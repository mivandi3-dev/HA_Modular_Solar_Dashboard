"""HTTP API poslužitelja (api.cpp + dijelovi bridge.cpp) – dashboard add-on je jedini klijent.

Prijava: zaglavlje `Authorization: Bearer <api_token>` (ključ iz /share/solarni/api_token ili opcije add-ona). Korisnika
nema – korisnike i prijavu vodi Home Assistant (Ingress dashboarda). 10 pogrešnih ključeva s iste adrese u 10 min → 429.
Jezik poruka: zaglavlje X-Solari-Language."""
from __future__ import annotations

import asyncio
import hmac
import tempfile
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiohttp import web

from . import API_VERSION, VERSION, i18n
from .config import HA_ENTITY_KEYS, is_serial_device, normalize_port, validate_form
from .core import Core
from .devices import read_plant
from .i18n import fmt_num, tr
from .images import KINDS
from .mailer import send_mail
from .alerts import test_message
from .netinfo import interface_names, list_interfaces, reaches, source_ip
from .report import build_report, report_csv
from .serialio import list_serial_ports
from .smartlogger import import_perfmg_days, parse_perfmg_day, read_perfmg_day
from .storage import Db
from .util import iso_date, local_date, log, now
from . import weather

FAIL_WINDOW_S, MAX_FAILURES, BLOCK_S = 600, 10, 600
MAX_UPLOAD = 200 * 1024 * 1024
CORE: web.AppKey[Core] = web.AppKey("core", Core)


def ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": True, "message": message, **extra}


def fail(message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "message": message, **extra}


class RateLimit:
    def __init__(self) -> None:
        self.failures: dict[str, tuple[int, float, float]] = {}  # ip → (broj, početak, blokirano do)

    def blocked(self, ip: str) -> bool:
        f = self.failures.get(ip)
        return bool(f and f[2] > time.time())

    def fail(self, ip: str) -> None:
        t = time.time()
        count, start, until = self.failures.get(ip, (0, t, 0.0))
        if t - start > FAIL_WINDOW_S:
            count, start, until = 0, t, 0.0
        count += 1
        if count >= MAX_FAILURES:
            until = t + BLOCK_S
            log.warning("API: previše pogrešnih ključeva s adrese %s – blokirano %d min", ip, BLOCK_S // 60)
        self.failures[ip] = (count, start, until)
        if len(self.failures) > 10_000:  # zaštita memorije: brišu se istekli zapisi
            self.failures = {k: v for k, v in self.failures.items() if v[2] > t or t - v[1] <= FAIL_WINDOW_S}


def _sync(fn: Callable[..., Any]) -> Callable[[web.Request], Awaitable[web.StreamResponse]]:
    """Blokirajući rad (mreža, baza, slike) u radnoj niti; jezik zahtjeva prelazi u nit (asyncio.to_thread kopira kontekst)."""
    async def handler(request: web.Request) -> web.StreamResponse:
        result = await asyncio.to_thread(fn, request.app[CORE], request, await _body(request))
        return result if isinstance(result, web.StreamResponse) else web.json_response(result)
    return handler


async def _body(request: web.Request) -> Any:
    if request.method not in ("POST", "PUT"):
        return None
    if request.content_type == "application/json":
        try:
            return await request.json()
        except ValueError:
            raise web.HTTPBadRequest(text='{"error":"bad_request"}', content_type="application/json")
    return await request.read()


# ---------------------------------------------------------------- podaci
def get_dashboard(core: Core, _r: web.Request, _b: Any) -> dict[str, Any]:
    return core.dashboard()


def get_image(core: Core, r: web.Request, _b: Any) -> web.StreamResponse:
    kind = r.match_info["kind"]
    if kind not in KINDS:
        raise web.HTTPNotFound()
    path = core.images.path(kind)
    if not path.exists():
        raise web.HTTPNotFound()
    return web.Response(body=path.read_bytes(), content_type=core.images.content_type(kind),
                        headers={"Cache-Control": "private, max-age=86400"})


def _month(r: web.Request) -> tuple[int, int]:
    try:
        y, m = int(r.query.get("year", "")), int(r.query.get("month", ""))
    except ValueError:
        raise web.HTTPBadRequest(text='{"error":"bad_month"}', content_type="application/json")
    if not (2000 <= y <= 2100 and 1 <= m <= 12):
        raise web.HTTPBadRequest(text='{"error":"bad_month"}', content_type="application/json")
    return y, m


def get_report(core: Core, r: web.Request, _b: Any) -> dict[str, Any]:
    y, m = _month(r)
    try:
        return ok("", report=build_report(core.data, core.settings(), y, m))
    except RuntimeError as e:
        return fail(str(e))


def get_report_csv(core: Core, r: web.Request, _b: Any) -> web.StreamResponse:
    y, m = _month(r)
    s = core.settings()
    try:
        body = report_csv(build_report(core.data, s, y, m))
    except RuntimeError as e:
        return web.json_response(fail(str(e)), status=400)
    name = "".join(c if c.isalnum() or c in "-_." else "_" for c in f"{s['plant_name']}-{y}-{m:02}.csv")
    return web.Response(body=body, content_type="text/csv", charset="utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})


def get_state(core: Core, _r: web.Request, _b: Any) -> dict[str, Any]:
    return core.state()


# ---------------------------------------------------------------- postavke
def post_settings(core: Core, _r: web.Request, form: Any) -> dict[str, Any]:
    if not isinstance(form, dict):
        return fail(tr("Provjerite označena polja."))
    new, errors = validate_form(form, core.settings(), interface_names())
    if not new:
        return fail(tr("Provjerite označena polja."), errors=errors)
    try:
        core.apply_settings(new)
    except OSError as e:
        return fail(tr("Postavke nisu spremljene: {error}", {"error": e}))
    return ok(tr("Postavke su spremljene."), settings=core.state()["settings"])


def _form_device(core: Core, form: dict[str, Any]) -> dict[str, Any]:
    s = core.settings()

    def num(key: str, default: int) -> int:
        v = form.get(key, default)
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    s.update({"modbus_host": str(form.get("modbus_host", "")).strip(), "modbus_port": num("modbus_port", 502),
              "modbus_unit_id": num("modbus_unit_id", 0), "meter_unit_id": num("meter_unit_id", 0),
              "device_type": form.get("device_type", "logger"), "inverter_units": str(form.get("inverter_units", "1")),
              "device_profile": form.get("device_profile", s["device_profile"]),
              "logger_serial": str(form.get("logger_serial", s["logger_serial"])).strip(),
              "logger_interface": form.get("logger_interface", ""),
              "serial_port": ",".join(normalize_port(p) for p in str(form.get("serial_port", s["serial_port"])).split(",") if p.strip()),
              "serial_baud": num("serial_baud", s["serial_baud"])})
    for key in HA_ENTITY_KEYS:
        if isinstance(form.get(key), str):
            s[key] = form[key].strip()
    for key in ("meter_invert", "meter_export_positive"):
        if isinstance(form.get(key), bool):
            s[key] = form[key]
    return s


def post_test_logger(core: Core, _r: web.Request, form: Any) -> dict[str, Any]:
    form = form if isinstance(form, dict) else {}
    s = _form_device(core, form)
    serial = is_serial_device(s["device_type"], s["device_profile"])
    try:
        p = read_plant(s)
    except Exception as e:  # noqa: BLE001
        hint = ""
        if s["logger_interface"] and reaches(s["logger_interface"], s["modbus_host"]) is False:
            hint = " " + tr("Napomena: {host} nije u mreži kartice „{iface}“ – provjerite IP adresu kartice ili postoji li "
                            "ruta do uređaja.", {"host": s["modbus_host"], "iface": s["logger_interface"]})
        return fail(str(e) + hint)
    r = p.reading
    today = "—" if r.e_daily_kwh < 0 else fmt_num(r.e_daily_kwh, 1)
    total = "—" if r.e_total_kwh < 0 else fmt_num(r.e_total_kwh, 0)
    meter = ""
    if p.meter_error:
        meter = " · " + tr("mjerač nije odgovorio ({error})", {"error": p.meter_error})
    elif p.load_kw is not None:
        meter = " · " + tr("mjerač {kw} kW", {"kw": fmt_num(p.load_kw, 2)})
    src = None if serial else source_ip(s["logger_interface"])
    via = (" " + tr("na {port}", {"port": s["serial_port"] or "USB"}) if serial
           else " " + tr("preko {ip}", {"ip": src}) if src else "")
    if "battery_soc" in p.extra or "battery_v" in p.extra:
        parts = []
        if "battery_soc" in p.extra:
            parts.append(fmt_num(p.extra["battery_soc"], 0) + " %")
        if "battery_v" in p.extra:
            parts.append(fmt_num(p.extra["battery_v"], 1) + " V")
        meter += " · " + tr("baterija {b}", {"b": " / ".join(parts)})
    device = p.device_name or (tr("Logger") if s["device_type"] == "logger" else tr("Inverter"))
    return ok(tr("{device} odgovara{via}: snaga {kw} kW · danas {today} kWh · ukupno {total} kWh",
                 {"device": device, "via": via, "kw": fmt_num(r.power_kw, 2), "today": today, "total": total}) + meter)


def _float(form: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(str(form.get(key, default)).replace(",", "."))
    except ValueError:
        return default


def post_test_internet(_core: Core, _r: web.Request, form: Any) -> dict[str, Any]:
    form = form if isinstance(form, dict) else {}
    try:
        w = weather.fetch(_float(form, "weather_lat", 45.815), _float(form, "weather_lon", 15.982),
                          source_ip(form.get("internet_interface", "")))
    except RuntimeError as e:
        return fail(tr("Internet nije dostupan: {error}", {"error": e}))
    return ok(tr("Internet radi – prognoza: {temp} °C, {label}, sunčevo zračenje {rad} W/m²",
                 {"temp": fmt_num(w["temperature"], 0), "label": tr(weather.weather_label(w["code"])),
                  "rad": fmt_num(w["radiation_wm2"], 0)}))


def post_geocode(_core: Core, _r: web.Request, body: Any) -> dict[str, Any]:
    body = body if isinstance(body, dict) else {}
    name = str(body.get("name", ""))
    try:
        places = weather.geocode(name, str(body.get("language", "hr")), source_ip(str(body.get("interface", ""))))
    except RuntimeError as e:
        return fail(tr("Internet nije dostupan: {error}", {"error": e}))
    if not places:
        return fail(tr("Mjesto „{name}” nije pronađeno.", {"name": name}))
    return ok("", places=places)


def post_test_email(core: Core, _r: web.Request, form: Any) -> dict[str, Any]:
    form = form if isinstance(form, dict) else {}
    new, errors = validate_form(form, core.settings(), interface_names())
    s = core.settings()
    if not new:
        mail_keys = ("alert_emails", "smtp_host", "smtp_port", "smtp_from", "smtp_user", "mail_provider", "resend_api_key")
        if any(k in errors for k in mail_keys):
            return fail(tr("Provjerite označena polja."), errors=errors)
    else:
        s = new  # ostala polja obrasca ne smiju spriječiti probnu poruku
    secret = form.get("resend_api_key" if s["mail_provider"] == "resend" else "smtp_password") or None
    try:
        m = test_message(s, now())
        to = send_mail(s, m.subject, m.body, str(secret).strip() if secret else None)
    except Exception as e:  # noqa: BLE001
        return fail(str(e))
    return ok(tr("Probna poruka poslana na: {to}", {"to": ", ".join(to)}))


# ---------------------------------------------------------------- slike i uvoz (tijelo zahtjeva = sadržaj datoteke)
def post_image(core: Core, r: web.Request, data: Any) -> dict[str, Any]:
    kind = r.match_info["kind"]
    if kind not in KINDS:
        return fail(tr("Nepoznata slika."))
    if not isinstance(data, (bytes, bytearray)) or not data:
        return fail(tr("Datoteka nije slika (podržano: JPG, PNG, WebP)."))
    try:
        info = core.images.replace(kind, bytes(data))
    except RuntimeError as e:
        return fail(str(e))
    log.info("Slika %s promijenjena", kind)
    return ok(info.pop("message"), image=info)


def delete_image(core: Core, r: web.Request, _b: Any) -> dict[str, Any]:
    kind = r.match_info["kind"]
    if kind not in KINDS:
        return fail(tr("Nepoznata slika."))
    core.images.reset(kind)
    return ok(tr("Vraćena je izvorna slika."), image=core.images.info(kind))


def post_import_history(core: Core, _r: web.Request, data: Any) -> dict[str, Any]:
    if not isinstance(data, (bytes, bytearray)) or not data:
        return fail(tr("Odabrana datoteka nije baza Solarnog monitora (nema tablice readings)."))
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "import.db"
        src.write_bytes(data)
        try:
            with Db(core.db_file) as db:
                added = db.import_history(src)
        except RuntimeError as e:
            return fail(str(e))
    core.data.invalidate()
    log.info("Uvezeno %d očitanja iz prenesene baze", added)
    return ok(tr("Uvezeno {n} očitanja.", {"n": fmt_num(added, 0)}), db=core.data.db_info())


def post_import_smartlogger(core: Core, r: web.Request, data: Any) -> dict[str, Any]:
    if not isinstance(data, (bytes, bytearray)) or not data:
        return fail(tr("Datoteka nije izvoz SmartLoggera."))
    try:
        days = parse_perfmg_day(read_perfmg_day(r.headers.get("X-Filename", ""), bytes(data)))
        if not days:
            return fail(tr("U izvozu nema dnevne proizvodnje elektrane."))
        with Db(core.db_file) as db:
            res = import_perfmg_days(db, days, local_date(now()))
    except RuntimeError as e:
        return fail(str(e))
    core.data.invalidate()
    log.info("Izvoz SmartLoggera: uvezeno %d dana, preskočeno %d", res.imported, res.skipped)
    msg = (tr("Uvezeno {n} dana ({from} – {to}, {kwh} kWh).", {"n": res.imported, "from": iso_date(res.first), "to": iso_date(res.last),
                                                              "kwh": fmt_num(res.kwh, 0)})
           if res.imported and res.first and res.last else tr("Nema novih dana za uvoz."))
    if res.skipped:
        msg += " " + tr("Preskočeno {n} dana koji već imaju podatke u bazi.", {"n": res.skipped})
    return ok(msg, db=core.data.db_info(), imported=res.imported, skipped=res.skipped)


def get_sensors(core: Core, _r: web.Request, _b: Any) -> dict[str, Any]:
    """Sažetak za HA REST senzore / automatizacije (i kad poslužitelj ne radi kao add-on)."""
    d = core.data.dashboard(core.settings())
    rt = d["realtime"]
    return {"power_kw": rt["power_kw"], "day_kwh": rt["day_kwh"], "month_kwh": rt["month_kwh"], "total_kwh": rt["total_kwh"],
            "load_kw": rt["load_kw"], "running": rt["running"], "stale": rt["stale"], "updated_at": rt["updated_at"],
            **{k: v for k, v in rt["extra"].items() if isinstance(v, (int, float, bool))}}


# ---------------------------------------------------------------- aplikacija
def create_app(core: Core) -> web.Application:
    limiter = RateLimit()

    @web.middleware
    async def auth(request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]) -> web.StreamResponse:
        i18n.set_language(request.headers.get("X-Solari-Language"))
        if request.path == "/api/v1/ping":
            return await handler(request)
        ip = request.remote or "?"
        if limiter.blocked(ip):
            return web.json_response({"error": "too_many_attempts"}, status=429)
        header = request.headers.get("Authorization", "")
        token = header[7:].strip() if header.startswith("Bearer ") else ""
        if not token or not hmac.compare_digest(token.encode(), request.app[CORE].api_token.encode()):
            if token:
                limiter.fail(ip)
            return web.json_response({"error": "unauthorized"}, status=401, headers={"WWW-Authenticate": "Bearer"})
        try:
            return await handler(request)
        except web.HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 – detalji samo u zapisniku
            log.exception("API %s: %s", request.path, e)
            return web.json_response({"error": "internal"}, status=500)

    app = web.Application(middlewares=[auth], client_max_size=MAX_UPLOAD)
    app[CORE] = core

    async def ping(_r: web.Request) -> web.StreamResponse:
        # watchdog Supervisora: 503 kad nit pollera ne radi → Home Assistant ponovno pokrene add-on
        alive = core.poller.alive()
        return web.json_response({"app": "Solarni poslužitelj", "api": API_VERSION, "version": VERSION, "poller": alive},
                                 status=200 if alive else 503)

    async def info(_r: web.Request) -> web.StreamResponse:
        s = core.settings()
        return web.json_response({"app": "Solarni poslužitelj", "version": VERSION, "api": API_VERSION,
                                  "plant": s["plant_name"], "location": s["location"]})

    async def interfaces(_r: web.Request) -> web.StreamResponse:
        return web.json_response(await asyncio.to_thread(list_interfaces))

    async def serial_ports(_r: web.Request) -> web.StreamResponse:
        return web.json_response(await asyncio.to_thread(list_serial_ports))

    r = app.router
    r.add_get("/api/v1/ping", ping)
    r.add_get("/api/v1/info", info)
    r.add_get("/api/v1/dashboard", _sync(get_dashboard))
    r.add_get("/api/v1/sensors", _sync(get_sensors))
    r.add_get("/api/v1/images/{kind}", _sync(get_image))
    r.add_post("/api/v1/images/{kind}", _sync(post_image))
    r.add_delete("/api/v1/images/{kind}", _sync(delete_image))
    r.add_get("/api/v1/report", _sync(get_report))
    r.add_get("/api/v1/report.csv", _sync(get_report_csv))
    r.add_get("/api/v1/state", _sync(get_state))
    r.add_get("/api/v1/interfaces", interfaces)
    r.add_get("/api/v1/serial_ports", serial_ports)
    r.add_post("/api/v1/settings", _sync(post_settings))
    r.add_post("/api/v1/test_logger", _sync(post_test_logger))
    r.add_post("/api/v1/test_internet", _sync(post_test_internet))
    r.add_post("/api/v1/test_email", _sync(post_test_email))
    r.add_post("/api/v1/geocode", _sync(post_geocode))
    r.add_post("/api/v1/import/history", _sync(post_import_history))
    r.add_post("/api/v1/import/smartlogger", _sync(post_import_smartlogger))

    async def on_startup(_app: web.Application) -> None:
        core.poller.start()

    async def on_cleanup(_app: web.Application) -> None:
        await asyncio.to_thread(core.poller.stop)
        core.close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app
