"""Dashboard add-on: poslužuje web sučelje (Ingress) i izvršava pozive mosta (window.pywebview.api.* → POST api/bridge/<metoda>).

Kao Windows klijent u načinu „poslužitelj”: raspored widgeta i postavke prikaza (tema, paleta, ikone, izgled, jezik,
noćni način, broj dana prognoze) čuva lokalno u /data, a podatke, postavke uređaja/elektrane/obavijesti, izvještaje,
slike i uvoz povijesti proksira Solarnom poslužitelju (SOLARI_SERVER_URL, ključ API-ja).

Prijava: Home Assistant (Ingress) – add-on prima promet samo s Ingress adrese Supervisora (172.30.32.2), osim
izbornog pregleda iz mreže (zaseban port, pristupni ključ u zaglavlju X-Solari-View-Key, samo čitanje)."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiohttp
from aiohttp import web

from . import VERSION, i18n
from .i18n import tr
from .layout import MAX_PAGES, ROTATE_CHOICES, Catalog, Layout, validate_layout
from .util import log, read_json, write_json

DISPLAY_KEYS = ("theme", "palette", "icon_theme", "design", "hero_photo", "language", "hide_idle_cursor", "night_mode",
                "night_from", "night_to", "forecast_days")
PIN_ITERATIONS = 200_000  # isto kao Windows verzija (config.cpp) – hash je prenosiv
LAYOUT_UNLOCK_S = 10 * 60
SETTINGS_UNLOCK_S = 30 * 60
PIN_MAX_ATTEMPTS, PIN_LOCKOUT_S = 5, 60
INGRESS_PEERS = ("172.30.32.2", "127.0.0.1", "::1")
SERVER_TIMEOUT = aiohttp.ClientTimeout(total=60)
LONG_TIMEOUT = aiohttp.ClientTimeout(total=300)  # uvoz velike baze


def hash_pin(pin: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    return "pbkdf2$" + salt.hex() + "$" + hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PIN_ITERATIONS, 32).hex()


def check_pin(pin: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        return hmac.compare_digest(hash_pin(pin, bytes.fromhex(salt)).split("$")[2], digest)
    except ValueError:
        return False


class ServerError(RuntimeError):
    pass


class Dashboard:
    def __init__(self, data_dir: Path, web_dir: Path, server_url: str, token: str, token_file: Path | None) -> None:
        self.data_dir, self.web_dir = data_dir, web_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self.server_url = server_url.rstrip("/")
        self._token, self.token_file = token, token_file
        self.local_file = data_dir / "display.json"
        self.catalog = Catalog(web_dir / "catalog.json")
        self.layout = Layout(self.catalog, data_dir / "layout.json")
        self.session: aiohttp.ClientSession | None = None
        self.unlocks: dict[str, tuple[float, bool]] = {}  # oznaka → (vrijedi do, i postavke)
        self.pin_failures, self.pin_locked_until = 0, 0.0
        self.last_dashboard: dict[str, Any] | None = None
        self.view_failures: dict[str, tuple[int, float, float]] = {}

    # ------------------------------------------------------------ lokalne postavke
    def local(self) -> dict[str, Any]:
        j = read_json(self.local_file, {})
        return j if isinstance(j, dict) else {}

    def save_local(self, values: dict[str, Any]) -> None:
        write_json(self.local_file, {**self.local(), **values}, private=True)

    def language(self) -> str:
        return self.local().get("language") or "hr"

    # ------------------------------------------------------------ poslužitelj
    def token(self) -> str:
        if self._token:
            return self._token
        if self.token_file:
            try:
                return self.token_file.read_text().strip()
            except OSError:
                return ""
        return ""

    async def call(self, method: str, path: str, json_body: Any = None, data: bytes | None = None,
                   headers: dict[str, str] | None = None, raw: bool = False, timeout: aiohttp.ClientTimeout = SERVER_TIMEOUT) -> Any:
        assert self.session
        h = {"Authorization": f"Bearer {self.token()}", "X-Solari-Language": self.language(), **(headers or {})}
        try:
            async with self.session.request(method, self.server_url + path, json=json_body, data=data, headers=h,
                                            timeout=timeout) as resp:
                if resp.status == 401:
                    raise ServerError(tr("Poslužitelj je odbio pristupni ključ – provjerite api_token u postavkama add-ona."))
                if raw:
                    return resp.status, resp.headers.get("Content-Type", ""), await resp.read(), dict(resp.headers)
                if resp.status >= 400 and resp.content_type != "application/json":
                    raise ServerError(f"HTTP {resp.status}")
                return await resp.json()
        except aiohttp.ClientError as e:
            raise ServerError(tr("Poslužitelj ne odgovara.") + f" ({self.server_url}: {e})") from e
        except asyncio.TimeoutError as e:
            raise ServerError(tr("Poslužitelj ne odgovara.") + f" ({self.server_url})") from e

    # ------------------------------------------------------------ PIN
    def pin_hash(self) -> str:
        return self.local().get("settings_pin_hash", "")

    def unlocked(self, token: str, settings: bool) -> bool:
        if not self.pin_hash():
            return True
        until, for_settings = self.unlocks.get(token, (0.0, False))
        return until > time.time() and (for_settings or not settings)

    def verify_pin(self, pin: str, settings: bool) -> dict[str, Any]:
        t = time.time()
        if t < self.pin_locked_until:
            return {"ok": False, "message": tr("Previše pogrešnih pokušaja. Pokušajte za {s} s.", {"s": int(self.pin_locked_until - t)})}
        if not check_pin(pin, self.pin_hash()):
            log.warning("Pogrešan PIN za postavke")
            self.pin_failures += 1
            if self.pin_failures >= PIN_MAX_ATTEMPTS:
                self.pin_failures, self.pin_locked_until = 0, t + PIN_LOCKOUT_S
            return {"ok": False, "message": tr("Pogrešan PIN.")}
        self.pin_failures = 0
        token = secrets.token_urlsafe(24)
        self.unlocks = {k: v for k, v in self.unlocks.items() if v[0] > t}
        self.unlocks[token] = (t + (SETTINGS_UNLOCK_S if settings else LAYOUT_UNLOCK_S), settings)
        return {"ok": True, "message": tr("Otključano."), "unlock_token": token}

    # ------------------------------------------------------------ podaci za dashboard
    def images_local(self, images: dict[str, str]) -> dict[str, str]:
        """/api/v1/images/hero?v=1 → img/hero?v=1 (relativno – radi i iza Ingress putanje)."""
        out = {}
        for kind, url in images.items():
            q = url.split("?", 1)[1] if "?" in url else ""
            out[kind] = f"img/{kind}" + (f"?{q}" if q else "")
        return out

    async def dashboard(self) -> dict[str, Any]:
        try:
            d = await self.call("GET", "/api/v1/dashboard")
            if "realtime" not in d:
                raise ServerError(str(d.get("error", "?")))
            self.last_dashboard = d
        except ServerError:
            if not self.last_dashboard:
                raise
            d = dict(self.last_dashboard)  # zadnji podaci ostaju na ekranu, oznaka „nedostupno”
            d["realtime"] = {**d["realtime"], "stale": True, "running": False}
        d = dict(d)
        d["settings"] = {**d["settings"], **{k: v for k, v in self.local().items() if k in DISPLAY_KEYS}}
        d.update(Layout.as_json(self.layout.load()))
        d["images"] = self.images_local(d.get("images", {}))
        d["fullscreen"] = False
        return d

    async def editor(self) -> dict[str, Any]:
        caps = (self.last_dashboard or {}).get("capabilities", [])
        meter = bool(((self.last_dashboard or {}).get("settings") or {}).get("meter_unit_id"))
        return {"catalog": self.catalog.raw["widgets"], "categories": self.catalog.raw["categories"],
                "rotateChoices": list(ROTATE_CHOICES), "maxPages": MAX_PAGES, "cols": self.catalog.cols, "rows": self.catalog.rows,
                "hasMeter": meter, "fullscreen": False, "capabilities": caps, "sidebarOpen": False, "version": VERSION,
                **Layout.as_json(self.layout.load())}

    async def state(self, unlock_token: str) -> dict[str, Any]:
        lang = self.language()
        if not self.unlocked(unlock_token, True):
            return {"locked": True, "version": VERSION, "language": lang, "i18n": i18n.bundle(lang)}
        srv = await self.call("GET", "/api/v1/state")
        if "settings" not in srv:
            raise ServerError(str(srv.get("error", "?")))
        local = self.local()
        settings = {**srv["settings"], **{k: v for k, v in local.items() if k in DISPLAY_KEYS},
                    "pin_set": bool(local.get("settings_pin_hash")), "data_source": "local",
                    "remote_view": bool(local.get("remote_view", False)), "remote_port": int(local.get("remote_port", 8600))}
        lang = settings.get("language", lang)
        view_port = os.environ.get("SOLARI_VIEW_PORT_PUBLIC", "")
        return {
            "i18n": i18n.bundle(lang), "locked": False, "wizard": srv.get("wizard", False), "version": srv.get("version", VERSION),
            "panel": "", "settings": settings, "interfaces": srv.get("interfaces", []), "suggested": srv.get("suggested", {}),
            "screens": [], "scales": {"auto": "Automatski – prema veličini prozora"}, "autostart": False, "poller_task": True,
            "paths": srv.get("paths", {}), "db": srv.get("db", {}), "legacy_db": None, "smartlogger_import": True,
            "device_types": srv.get("device_types", []), "serial_ports": srv.get("serial_ports", []),
            "device_profiles": srv.get("device_profiles", []), "images": srv.get("images", {}),
            "remote_urls": [f"http://<IP Home Assistanta>:{view_port}"] if view_port and local.get("remote_view") else [],
            "remote_view_key": local.get("remote_view_key", "") if local.get("remote_view") else "",
            "role": "client", "features": {"cloud": False}, "server": None,
            "ha": {"server_url": self.server_url, "poller": srv.get("poller", {}), "view_port": view_port},
        }

    async def save(self, form: dict[str, Any]) -> dict[str, Any]:
        pin_new = str(form.get("pin_new") or "").strip()
        if pin_new and not (pin_new.isdigit() and 4 <= len(pin_new) <= 8):
            return {"ok": False, "message": tr("Provjerite označena polja."), "errors": {"pin_new": tr("PIN ima 4 do 8 znamenki.")}}
        res = await self.call("POST", "/api/v1/settings", json_body={k: v for k, v in form.items() if k not in ("pin_new", "pin_clear")})
        if not res.get("ok"):
            return res
        saved = res.get("settings", {})
        local: dict[str, Any] = {k: saved[k] for k in DISPLAY_KEYS if k in saved}
        local["remote_view"] = bool(form.get("remote_view"))
        try:
            port = int(form.get("remote_port", 8600))
            local["remote_port"] = port if 1024 <= port <= 65535 else 8600
        except (TypeError, ValueError):
            local["remote_port"] = 8600
        if local["remote_view"] and not self.local().get("remote_view_key"):
            local["remote_view_key"] = new_view_key()
        if form.get("pin_clear"):
            local["settings_pin_hash"] = ""
        elif pin_new:
            local["settings_pin_hash"] = hash_pin(pin_new)
        self.save_local(local)
        return {"ok": True, "message": res.get("message", tr("Postavke su spremljene."))}

    # ------------------------------------------------------------ pregled iz mreže
    def view_allowed(self, ip: str, key: str) -> bool | None:
        """None = blokirano (429), False = pogrešan ključ, True = u redu."""
        t = time.time()
        count, start, until = self.view_failures.get(ip, (0, t, 0.0))
        if until > t:
            return None
        expected = self.local().get("remote_view_key", "")
        if expected and self.local().get("remote_view") and hmac.compare_digest(key.encode(), expected.encode()):
            return True
        if t - start > 600:
            count, start = 0, t
        count += 1
        self.view_failures[ip] = (count, start, t + 600 if count >= 10 else 0.0)
        return False


def new_view_key() -> str:
    return base64.b32encode(secrets.token_bytes(16)).decode().rstrip("=")


# ---------------------------------------------------------------- most (bridge)
Handler = Callable[[Dashboard, list[Any], str], Awaitable[Any]]


def _arg(args: list[Any], i: int, default: Any = None) -> Any:
    return args[i] if i < len(args) else default


def _int(args: list[Any], i: int, default: int = 0) -> int:
    try:
        return int(_arg(args, i, default))
    except (TypeError, ValueError):
        return default


LAYOUT_CHANGES = {"save_layout", "remove_page", "set_rotation", "reset_layout"}
PUBLIC = {"get_dashboard", "get_editor", "get_state", "unlock", "unlock_layout", "layout_state", "get_i18n", *LAYOUT_CHANGES}


async def _layout_call(d: Dashboard, method: str, args: list[Any]) -> Any:
    if method == "save_layout":
        items, errors = validate_layout(d.catalog, _arg(args, 0, []))
        if errors:
            return {"ok": False, "message": errors[0]}
        page = _int(args, 1)
        try:
            d.layout.save_page(items, page)
        except RuntimeError as e:
            return {"ok": False, "message": str(e)}
        log.info("Raspored widgeta spremljen (stranica %d, %d widgeta)", page + 1, len(items))
        return {"ok": True, "layout": items}
    if method == "remove_page":
        return {"ok": True, **Layout.as_json(d.layout.remove_page(_int(args, 0, -1)))}
    if method == "set_rotation":
        try:
            return {"ok": True, **Layout.as_json(d.layout.set_rotation(_int(args, 0, -1)))}
        except RuntimeError as e:
            return {"ok": False, "message": str(e)}
    return {"ok": True, **Layout.as_json(d.layout.reset())}


async def dispatch(d: Dashboard, method: str, args: list[Any], unlock_token: str) -> Any:
    i18n.set_language(d.language())
    if method in LAYOUT_CHANGES:
        if not d.unlocked(unlock_token, False):  # 5.0.2 (W-02): izmjene rasporeda samo uz PIN postavki
            return {"ok": False, "error": "layout_locked", "message": tr("Raspored je zaključan – upišite PIN postavki.")}
        return await _layout_call(d, method, args)
    if method == "get_dashboard":
        return await d.dashboard()
    if method == "get_editor":
        return await d.editor()
    if method == "layout_state":
        return {"unlocked": d.unlocked(unlock_token, False)}
    if method in ("unlock", "unlock_layout"):
        if not d.pin_hash():
            return {"ok": True, "message": tr("Otključano."), "unlock_token": ""}
        return d.verify_pin(str(_arg(args, 0, "")), method == "unlock")
    if method == "get_state":
        return await d.state(unlock_token)
    if method == "get_i18n":
        return i18n.bundle(str(_arg(args, 0, "hr")))
    if not d.unlocked(unlock_token, True):
        raise PermissionError(tr("Postavke su zaključane PIN-om."))
    if method == "interfaces":
        return await d.call("GET", "/api/v1/interfaces")
    if method == "serial_ports":
        return await d.call("GET", "/api/v1/serial_ports")
    if method in ("test_logger", "test_internet", "test_email"):
        return await d.call("POST", f"/api/v1/{method}", json_body=_arg(args, 0, {}), timeout=LONG_TIMEOUT)
    if method == "geocode":
        return await d.call("POST", "/api/v1/geocode", json_body={"name": _arg(args, 0, ""), "interface": _arg(args, 1, ""),
                                                                  "language": _arg(args, 2, "hr")})
    if method == "save":
        return await d.save(_arg(args, 0, {}))
    if method == "get_report":
        return await d.call("GET", f"/api/v1/report?year={_int(args, 0)}&month={_int(args, 1)}")
    if method == "reset_image":
        return await d.call("DELETE", f"/api/v1/images/{_arg(args, 0, '')}")
    if method == "remote_view_new_key":
        key = new_view_key()
        d.save_local({"remote_view_key": key})
        log.info("Pregled iz mreže: izrađen novi pristupni ključ")
        return {"ok": True, "message": tr("Novi pristupni ključ je izrađen – stari više ne vrijedi."), "remote_view_key": key}
    if method in ("open_folder", "close", "set_sidebar", "set_display", "reload", "quit", "open_logs", "window_control", "window_state"):
        return None  # radnje prozora izvodi preglednik (ha-bridge.js)
    raise ValueError("Nepoznata metoda: " + method)


# ---------------------------------------------------------------- web aplikacija
DASH: web.AppKey[Dashboard] = web.AppKey("dash", Dashboard)
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}


def create_ingress_app(d: Dashboard, ingress_only: bool) -> web.Application:
    @web.middleware
    async def guard(request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]) -> web.StreamResponse:
        if ingress_only and request.remote not in INGRESS_PEERS:
            return web.Response(status=403, text="403 – samo preko Home Assistanta (Ingress)")
        resp = await handler(request)
        if not resp.prepared:
            resp.headers.update({k: v for k, v in SECURITY_HEADERS.items() if k not in resp.headers})
        return resp

    app = web.Application(middlewares=[guard], client_max_size=200 * 1024 * 1024)
    app[DASH] = d

    async def bridge(request: web.Request) -> web.StreamResponse:
        method = request.match_info["method"]
        try:
            body = await request.json()
        except ValueError:
            body = {}
        args = body.get("args", []) if isinstance(body, dict) else []
        try:
            result = await dispatch(d, method, args if isinstance(args, list) else [], request.headers.get("X-Solari-Unlock", ""))
            return web.json_response({"ok": True, "result": result})
        except (ServerError, PermissionError, ValueError) as e:
            return web.json_response({"ok": False, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            log.exception("Poziv %s: %s", method, e)
            return web.json_response({"ok": False, "error": tr("Greška")})

    async def image(request: web.Request) -> web.StreamResponse:
        kind = request.match_info["kind"]
        if kind not in ("hero", "drawing", "logo"):
            raise web.HTTPNotFound()
        status, ctype, body, _ = await d.call("GET", f"/api/v1/images/{kind}", raw=True)
        if status != 200:
            raise web.HTTPNotFound()
        return web.Response(body=body, content_type=ctype.split(";")[0], headers={"Cache-Control": "private, max-age=86400"})

    async def upload(request: web.Request) -> web.StreamResponse:
        """Datoteka iz preglednika (umjesto Windows dijaloga): slika, solar.db ili log.zip SmartLoggera."""
        if not d.unlocked(request.headers.get("X-Solari-Unlock", ""), True):
            return web.json_response({"ok": False, "message": tr("Postavke su zaključane PIN-om.")})
        what, kind = request.match_info["what"], request.query.get("kind", "")
        paths = {"image": f"/api/v1/images/{kind}", "history": "/api/v1/import/history", "smartlogger": "/api/v1/import/smartlogger"}
        if what not in paths or (what == "image" and kind not in ("hero", "drawing", "logo")):
            raise web.HTTPNotFound()
        data = await request.read()
        name = request.headers.get("X-Filename", "")[:200]
        i18n.set_language(d.language())
        try:
            res = await d.call("POST", paths[what], data=data, timeout=LONG_TIMEOUT,
                               headers={"Content-Type": "application/octet-stream", "X-Filename": name})
        except ServerError as e:
            res = {"ok": False, "message": str(e)}
        return web.json_response(res)

    async def report_csv(request: web.Request) -> web.StreamResponse:
        if not d.unlocked(request.query.get("unlock", ""), True):
            raise web.HTTPForbidden()
        y, m = request.query.get("year", ""), request.query.get("month", "")
        status, ctype, body, headers = await d.call("GET", f"/api/v1/report.csv?year={y}&month={m}", raw=True)
        return web.Response(status=status, body=body, content_type=ctype.split(";")[0] or "text/csv",
                            headers={"Content-Disposition": headers.get("Content-Disposition", "attachment")})

    async def index(_r: web.Request) -> web.StreamResponse:
        return web.FileResponse(d.web_dir / "index.html")

    async def ha_bridge(_r: web.Request) -> web.StreamResponse:
        return web.FileResponse(d.web_dir / "ha-bridge.js")  # most za Home Assistant umjesto WebView2 mosta

    app.router.add_get("/bridge.js", ha_bridge)
    app.router.add_post("/api/bridge/{method}", bridge)
    app.router.add_get("/img/{kind}", image)
    app.router.add_post("/api/upload/{what}", upload)
    app.router.add_get("/api/report.csv", report_csv)
    app.router.add_get("/", index)
    app.router.add_static("/", d.web_dir, show_index=False, append_version=False)
    _lifecycle(app, d)
    return app


def create_view_app(d: Dashboard) -> web.Application:
    """Pregled iz lokalne mreže (remote.cpp): obični preglednik (TV u predvorju) bez HA računa, samo čitanje, uz ključ."""
    app = web.Application()
    web_dir = d.web_dir

    async def check(request: web.Request) -> web.StreamResponse | None:
        ok = d.view_allowed(request.remote or "?", request.headers.get("X-Solari-View-Key", ""))
        if ok is None:
            return web.json_response({"error": "too_many_attempts"}, status=429)
        if not ok:
            return web.json_response({"error": "unauthorized"}, status=401)
        return None

    async def dashboard(request: web.Request) -> web.StreamResponse:
        denied = await check(request)
        if denied:
            return denied
        data = await d.dashboard()
        data["images"] = {k: f"/api/image/{k}?{v.split('?', 1)[1]}" if "?" in v else f"/api/image/{k}" for k, v in data["images"].items()}
        return web.json_response(data)

    async def image(request: web.Request) -> web.StreamResponse:
        denied = await check(request)
        if denied:
            return denied
        kind = request.match_info["kind"]
        if kind not in ("hero", "drawing", "logo"):
            raise web.HTTPNotFound()
        status, ctype, body, _ = await d.call("GET", f"/api/v1/images/{kind}", raw=True)
        return web.Response(status=status, body=body, content_type=ctype.split(";")[0])

    async def root(_r: web.Request) -> web.StreamResponse:
        raise web.HTTPFound("/web/index.html")

    async def bridge_js(_r: web.Request) -> web.StreamResponse:
        return web.FileResponse(web_dir / "bridge.js")  # izvorni most: grana „pregled iz mreže”

    app.router.add_get("/", root)
    app.router.add_get("/api/dashboard", dashboard)
    app.router.add_get("/api/image/{kind}", image)
    app.router.add_get("/web/bridge.js", bridge_js)
    app.router.add_static("/web/", web_dir, show_index=False)
    return app


def _lifecycle(app: web.Application, d: Dashboard) -> None:
    async def startup(_app: web.Application) -> None:
        d.session = aiohttp.ClientSession()

    async def cleanup(_app: web.Application) -> None:
        if d.session:
            await d.session.close()

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
