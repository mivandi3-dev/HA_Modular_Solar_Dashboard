"""Cijeli put: dashboard (most) → poslužitelj (API s ključem) – oba kao stvarne aiohttp aplikacije."""
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from solari_dashboard.app import Dashboard, check_pin, create_ingress_app, create_view_app, hash_pin
from solari_dashboard.layout import Catalog, validate_layout
from solari_server.core import Core
from solari_server.api import create_app

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "solarni_dashboard" / "app" / "web"
ASSETS = ROOT / "solarni_server" / "app" / "assets"


@pytest.fixture
async def stack(tmp_path):
    core = Core(tmp_path / "srv", ASSETS, tmp_path / "share" / "api_token", publish_sensors=False)
    core.poller.start = lambda: None  # bez uređaja
    server = TestClient(TestServer(create_app(core)))
    await server.start_server()
    dash = Dashboard(tmp_path / "dash", WEB, str(server.make_url("")), "", tmp_path / "share" / "api_token")
    client = TestClient(TestServer(create_ingress_app(dash, ingress_only=False)))
    await client.start_server()
    yield core, server, dash, client
    await client.close()
    await server.close()


async def bridge(client, method, *args, unlock=""):
    r = await client.post(f"/api/bridge/{method}", json={"args": list(args)}, headers={"X-Solari-Unlock": unlock})
    return await r.json()


async def test_server_requires_token_and_rate_limits(stack):
    core, server, *_ = stack
    assert (await server.get("/api/v1/ping")).status == 200
    assert (await server.get("/api/v1/dashboard")).status == 401
    for _ in range(10):
        await server.get("/api/v1/dashboard", headers={"Authorization": "Bearer pogresno"})
    assert (await server.get("/api/v1/dashboard", headers={"Authorization": f"Bearer {core.api_token}"})).status == 429


async def test_dashboard_through_bridge_and_token_file(stack):
    core, _, dash, client = stack
    assert (Path(dash.token_file)).read_text() == core.api_token
    d = await bridge(client, "get_dashboard")
    assert d["ok"] and "realtime" in d["result"] and d["result"]["images"]["hero"].startswith("img/hero")
    assert "modbus_host" not in d["result"]["settings"]  # SMA-08
    img = await client.get(d["result"]["images"]["hero"].replace("img/", "/img/"))
    assert img.status == 200 and img.content_type == "image/jpeg"
    js = await client.get("/bridge.js")
    assert "SOLARI_HA" in await js.text()


async def test_settings_save_display_local_and_pin(stack):
    core, _, dash, client = stack
    st = (await bridge(client, "get_state"))["result"]
    assert st["wizard"] and not st["locked"] and st["role"] == "client"
    form = {**st["settings"], "theme": "light", "palette": "light", "language": "en", "pin_new": "1234", "modbus_host": "10.0.0.5"}
    res = (await bridge(client, "save", form))["result"]
    assert res["ok"], res
    assert core.settings()["modbus_host"] == "10.0.0.5" and core.configured()
    assert dash.local()["theme"] == "light" and dash.local()["language"] == "en"
    assert (await bridge(client, "get_state"))["result"]["locked"]
    assert not (await bridge(client, "test_logger", {}))["ok"]  # zaključano
    bad = (await bridge(client, "unlock", "0000"))["result"]
    assert not bad["ok"]
    good = (await bridge(client, "unlock", "1234"))["result"]
    assert good["ok"]
    st = (await bridge(client, "get_state", unlock=good["unlock_token"]))["result"]
    assert not st["locked"] and st["settings"]["pin_set"]


async def test_layout_lock_and_editor(stack):
    _, _, dash, client = stack
    dash.save_local({"settings_pin_hash": hash_pin("4321")})
    ed = (await bridge(client, "get_editor"))["result"]
    assert ed["maxPages"] == 6 and ed["pages"]
    locked = (await bridge(client, "save_layout", ed["pages"][0], 0))["result"]
    assert locked["error"] == "layout_locked"
    tok = (await bridge(client, "unlock_layout", "4321"))["result"]["unlock_token"]
    ok = (await bridge(client, "save_layout", ed["pages"][0], 1, unlock=tok))["result"]
    assert not ok["ok"]  # ista oznaka na drugoj stranici
    ok = (await bridge(client, "set_rotation", 30, unlock=tok))["result"]
    assert ok["ok"] and ok["rotateS"] == 30
    assert (await bridge(client, "get_state", unlock=tok))["result"]["locked"]  # raspored ne otključava postavke


async def test_upload_image_and_history(stack, tmp_path):
    core, _, dash, client = stack
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (1920, 320), (10, 120, 200)).save(buf, "JPEG")
    r = await (await client.post("/api/upload/image?kind=hero", data=buf.getvalue(), headers={"X-Filename": "a.jpg"})).json()
    assert r["ok"] and r["image"]["custom"]
    r = await (await client.post("/api/upload/history", data=b"nije baza")).json()
    assert not r["ok"]
    reset = await bridge(client, "reset_image", "hero")
    assert reset["result"]["ok"] and not reset["result"]["image"]["custom"]


async def test_view_port_needs_key(stack):
    _, _, dash, _ = stack
    view = TestClient(TestServer(create_view_app(dash)))
    await view.start_server()
    try:
        assert (await view.get("/api/dashboard")).status == 401
        dash.save_local({"remote_view": True, "remote_view_key": "KLJUC"})
        r = await view.get("/api/dashboard", headers={"X-Solari-View-Key": "KLJUC"})
        assert r.status == 200 and (await r.json())["images"]["hero"].startswith("/api/image/hero")
    finally:
        await view.close()


def test_pin_hash_format_compatible():
    h = hash_pin("2468")
    assert h.startswith("pbkdf2$") and len(h.split("$")[1]) == 32 and len(h.split("$")[2]) == 64
    assert check_pin("2468", h) and not check_pin("2469", h)


def test_layout_validation():
    cat = Catalog(WEB / "catalog.json")
    items, errors = validate_layout(cat, cat.default_layout)
    assert items and not errors
    first = dict(items[0])
    clash = {**first, "id": first["id"] + "x"}
    items2, errors2 = validate_layout(cat, [first, clash, {"type": "nepostoji", "x": 0, "y": 0, "w": 1, "h": 1}])
    assert len(items2) == 1 and len(errors2) == 2


async def test_ping_reports_dead_poller(stack):
    core, server, *_ = stack
    assert (await server.get("/api/v1/ping")).status == 200
    core.poller.alive = lambda: False
    assert (await server.get("/api/v1/ping")).status == 503  # watchdog Supervisora ponovno pokrene add-on
