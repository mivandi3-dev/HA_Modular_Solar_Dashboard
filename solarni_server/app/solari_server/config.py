"""Postavke poslužitelja (config.cpp) – ista imena polja kao Windows verzija, pa obrazac postavki (web/settings.js) radi isto.

Razlike za Home Assistant:
  * tajne (API ključ servisa Resend, lozinka SMTP-a) spremaju se u /data/secrets.json (samo vlasnik, 0600) umjesto DPAPI-ja –
    /data add-ona vidi samo taj add-on;
  * izvor podataka je uvijek uređaj (nema „cloud” načina – dashboard je zasebni add-on koji čita ovaj poslužitelj);
  * serijski portovi su Linux uređaji (/dev/ttyUSB0, /dev/serial/by-id/…) ili COMn (za Windows razvoj);
  * mrežna kartica prema uređaju smije biti „automatski” (Linux sam bira rutu).
"""
from __future__ import annotations

import copy
import math
import re
from pathlib import Path
from typing import Any

from . import i18n
from .i18n import tr
from .util import read_json, write_json

DEFAULTS: dict[str, Any] = {
    "device_type": "logger", "device_profile": "sungrow_sg", "logger_serial": "", "serial_port": "", "serial_baud": 0,
    "inverter_units": "1", "modbus_host": "192.168.5.199", "modbus_port": 502, "modbus_unit_id": 0, "poll_interval_s": 10,
    "meter_unit_id": 1, "meter_export_positive": True, "meter_invert": False,
    "logger_interface": "", "internet_interface": "",
    "plant_name": "Moja tvrtka d.o.o.", "location": "Zagreb, Hrvatska", "peak_power_kwp": 80.0, "co2_factor": 0.40,
    "commissioned": "11.2023.", "headline": "Solarna elektrana", "headline_running": "proizvodi *čistu energiju*",
    "headline_idle": "trenutno *miruje*", "speedo_max_kw": 80, "theme": "dark", "palette": "", "icon_theme": "classic",
    "design": "classic", "hero_photo": True, "language": "hr", "weather_lat": 45.815, "weather_lon": 15.982,
    "weather_city": "Zagreb, Hrvatska", "forecast_days": 5, "display_scale": "auto", "monitor": 0, "start_fullscreen": True,
    "hide_idle_cursor": True, "keep_awake": True, "backup_keep_days": 14, "price_kwh": 0.15, "feedin_price_kwh": 0.05,
    "currency": "€", "night_mode": "off", "night_from": "22:00", "night_to": "06:00", "remote_view": False, "remote_port": 8600,
    "alert_emails": "", "mail_provider": "resend", "resend_api_key_enc": "", "smtp_host": "", "smtp_port": 587,
    "smtp_security": "starttls", "smtp_user": "", "smtp_password_enc": "", "smtp_from": "", "alert_offline_min": 30,
    "alert_low_production": True, "alert_fault": True, "data_source": "local", "server_port": 8700,
    # HA: vrsta uređaja „homeassistant” – entiteti koje Home Assistant već čita (ha_api.py)
    "ha_power_entity": "", "ha_today_entity": "", "ha_total_entity": "", "ha_grid_entity": "", "ha_battery_soc_entity": "",
    "ha_battery_power_entity": "",
}
HA_ENTITY_KEYS = ("ha_power_entity", "ha_today_entity", "ha_total_entity", "ha_grid_entity", "ha_battery_soc_entity",
                  "ha_battery_power_entity")
SECRET_KEYS = ("resend_api_key_enc", "smtp_password_enc")

THEMES = ("dark", "light")
SCALES = ("auto", "fhd", "2k", "4k")
NIGHT_MODES = ("off", "dim", "screen_off")
SMTP_SECURITY = ("starttls", "ssl", "none")
MAIL_PROVIDERS = ("resend", "smtp")
PALETTES = ("", "ocean", "forest", "sunset", "midnight", "graphite", "contrast", "paper", "sky", "sand")
ICON_THEMES = ("classic", "neon", "iconset")
DESIGNS = ("classic", "aurora", "control", "daylight")
DEVICE_TYPES = ("logger", "inverter", "sunspec", "fronius", "vendor", "voltronic", "vedirect", "homeassistant")
BAUDS = (0, 2400, 9600, 19200, 115200)
MAX_RECIPIENTS = 20

_IP = re.compile(r"^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$")
_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,62})(\.[A-Za-z0-9][A-Za-z0-9-]{0,62})*$")
_DIGITS_DOTS = re.compile(r"^[\d.]+$")
_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_UNITS = re.compile(r"^\s*\d{1,3}\s*(,\s*\d{1,3}\s*)*$")
_RESEND = re.compile(r"^re_[A-Za-z0-9_-]{7,197}$")
_COM = re.compile(r"^COM([1-9]\d?|1\d\d|2[0-4]\d|25[0-6])$", re.I)
_DEV = re.compile(r"^/dev/[A-Za-z0-9._:+/-]{1,200}$")
_ENTITY = re.compile(r"^[a-z_]+\.[a-z0-9_]{1,200}$")


# ---------------------------------------------------------------- pomoćne provjere
def valid_host_name(host: str) -> bool:
    if not host or len(host) > 253:
        return False
    return bool(_IP.match(host)) or (bool(_HOST.match(host)) and not _DIGITS_DOTS.match(host))


def is_serial_port_name(name: str) -> bool:
    if _COM.match(name):
        return True
    return bool(_DEV.match(name)) and ".." not in name


def normalize_port(name: str) -> str:
    """COM3 velikim slovima; Linux putanje ostaju kakve jesu (razlikuju velika i mala slova)."""
    name = name.strip()
    return name.upper() if _COM.match(name) or name.upper() == "USB" else name


def parse_units(text: str) -> list[int] | None:
    if not _UNITS.match(text or ""):
        return None
    units: list[int] = []
    for part in text.split(","):
        unit = int(part.strip())
        if unit in units or unit > 247:
            return None
        units.append(unit)
    return units if 0 < len(units) <= 10 else None


def parse_logger_serial(text: str) -> int | None:
    if not text or len(text) > 10 or not text.isdigit():
        return None
    value = int(text)
    return value if 0 < value <= 0xFFFFFFFF else None


def parse_recipients(text: str) -> tuple[list[str] | None, str]:
    """(adrese, prva_neispravna) – adrese odvojene zarezom, točka-zarezom ili razmakom, bez ponavljanja, najviše 20."""
    out: list[str] = []
    for part in re.split(r"[,;\s]+", text or ""):
        if not part:
            continue
        if not _EMAIL.match(part):
            return None, part
        if part.lower() not in (o.lower() for o in out):
            out.append(part)
    if len(out) > MAX_RECIPIENTS:
        return None, ""
    return out, ""


def valid_resend_key(key: str) -> bool:
    return bool(_RESEND.match(key or ""))


def is_serial_device(device_type: str, profile: str) -> bool:
    from .vendors import find_vendor  # izbjegava kružni uvoz

    if device_type in ("voltronic", "vedirect"):
        return True
    p = find_vendor(profile) if device_type == "vendor" else None
    return bool(p and p.link == "serial")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if not isinstance(value, str):
        return None
    s = value.replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        d = float(s)
    except ValueError:
        return None
    return d if math.isfinite(d) else None


def _fmt_bound(v: float) -> str:
    return (str(int(v)) if v == int(v) else str(v)).replace(".", ",")


# ---------------------------------------------------------------- spremanje
class SettingsStore:
    """config.json (bez tajni) + secrets.json (0600) u mapi podataka poslužitelja."""

    def __init__(self, data_dir: Path) -> None:
        self.config_file = data_dir / "config.json"
        self.secrets_file = data_dir / "secrets.json"

    def exists(self) -> bool:
        return self.config_file.exists()

    def load(self) -> dict[str, Any]:
        raw = read_json(self.config_file, {}) or {}
        secrets = read_json(self.secrets_file, {}) or {}
        if isinstance(secrets, dict):
            for k in SECRET_KEYS:
                if k in secrets:
                    raw[k] = secrets[k]
        return settings_from_json(raw)

    def save(self, s: dict[str, Any]) -> None:
        old = read_json(self.config_file)
        if isinstance(old, dict):
            write_json(self.config_file.with_suffix(".json.bak"), old)
        write_json(self.secrets_file, {k: s.get(k, "") for k in SECRET_KEYS}, private=True)
        write_json(self.config_file, {k: v for k, v in s.items() if k not in SECRET_KEYS})


def settings_from_json(j: Any) -> dict[str, Any]:
    s = copy.deepcopy(DEFAULTS)
    if not isinstance(j, dict):
        return s
    for key, default in DEFAULTS.items():
        if key not in j or j[key] is None:
            continue
        v = j[key]
        if isinstance(default, bool):
            if isinstance(v, bool):
                s[key] = v
        elif isinstance(default, int):
            if isinstance(v, (int, float)) and not isinstance(v, bool) and float(v).is_integer():
                s[key] = int(v)
        elif isinstance(default, float):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                s[key] = float(v)
        elif isinstance(v, str):
            s[key] = v
    if "mail_provider" not in j:  # postavke bez polja: tko ima SMTP poslužitelj, ostaje na njemu
        s["mail_provider"] = "smtp" if s["smtp_host"] else "resend"
    fixes = {"palette": (PALETTES, ""), "icon_theme": (ICON_THEMES, "classic"), "design": (DESIGNS, "classic"),
             "mail_provider": (MAIL_PROVIDERS, "resend"), "night_mode": (NIGHT_MODES, "off"),
             "smtp_security": (SMTP_SECURITY, "starttls"), "theme": (THEMES, "dark"), "display_scale": (SCALES, "auto"),
             "language": (i18n.LANGUAGES, "hr"), "device_type": (DEVICE_TYPES, "logger")}
    for key, (allowed, fallback) in fixes.items():
        if s[key] not in allowed:
            s[key] = fallback
    if s["forecast_days"] not in (2, 3, 5):
        s["forecast_days"] = 5
    s["data_source"] = "local"
    return s


def to_form(s: dict[str, Any]) -> dict[str, Any]:
    form = {k: v for k, v in s.items() if k not in SECRET_KEYS}
    form["cloud_account"] = None
    form["pin_set"] = False  # PIN čuva dashboard (vidi solarni_dashboard)
    form["smtp_password_set"] = bool(s.get("smtp_password_enc"))
    form["resend_api_key_set"] = bool(s.get("resend_api_key_enc"))
    return form


# ---------------------------------------------------------------- obrazac
_NUMBERS = (
    ("modbus_port", True, 1, 65535), ("modbus_unit_id", True, 0, 247), ("meter_unit_id", True, 0, 247),
    ("poll_interval_s", True, 5, 3600), ("peak_power_kwp", False, 0.1, 100000), ("co2_factor", False, 0, 2),
    ("speedo_max_kw", True, 1, 100000), ("weather_lat", False, -90, 90), ("weather_lon", False, -180, 180),
    ("monitor", True, 0, 16), ("backup_keep_days", True, 0, 365), ("price_kwh", False, 0, 100),
    ("feedin_price_kwh", False, 0, 100), ("remote_port", True, 1024, 65535), ("smtp_port", True, 1, 65535),
    ("alert_offline_min", True, 0, 1440), ("server_port", True, 1024, 65535),
)
_TEXTS = (("plant_name", 1, 80), ("location", 0, 80), ("commissioned", 0, 20), ("headline", 1, 60),
          ("headline_running", 0, 60), ("headline_idle", 0, 60), ("currency", 1, 5), ("smtp_host", 0, 253),
          ("smtp_user", 0, 254), ("smtp_from", 0, 254))
_BOOLS = ("start_fullscreen", "hide_idle_cursor", "keep_awake", "remote_view", "alert_low_production", "alert_fault",
          "meter_export_positive", "meter_invert", "hero_photo")


def validate_form(form: dict[str, Any], current: dict[str, Any], interfaces: list[str]) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """Ista pravila kao validate_form u config.cpp. Vraća (nove postavke ili None, greške po poljima)."""
    from .vendors import find_vendor

    errors: dict[str, str] = {}
    s = copy.deepcopy(current)

    def text(key: str) -> str:
        v = form.get(key)
        return v.strip() if isinstance(v, str) else ""

    device = form.get("device_type", current["device_type"])
    profile = form.get("device_profile", current["device_profile"])
    serial_dev = is_serial_device(device, profile)
    if serial_dev:
        ports = [normalize_port(p) for p in str(form.get("serial_port", current["serial_port"])).replace(" ", "").split(",")]
        ok = bool(ports and ports[0])
        for one in ports:
            ok = ok and (is_serial_port_name(one) or (one == "USB" and device == "voltronic"))
        if not ok:
            errors["serial_port"] = tr("Izaberite serijski port (npr. COM3) ili USB.")
        s["serial_port"] = ",".join(ports)
        baud = form.get("serial_baud", current["serial_baud"])
        try:
            s["serial_baud"] = int(baud) if baud not in ("", None) else 0
        except (TypeError, ValueError):
            s["serial_baud"] = -1
        if s["serial_baud"] not in BAUDS:
            errors["serial_baud"] = tr("Brzina: 2400, 9600, 19200 ili 115200.")

    s["modbus_host"] = text("modbus_host")
    if serial_dev and not s["modbus_host"]:
        s["modbus_host"] = current["modbus_host"]
    ha_dev = device == "homeassistant"
    if ha_dev and not valid_host_name(s["modbus_host"]):
        s["modbus_host"] = current["modbus_host"]  # entiteti HA – IP adresa uređaja nije potrebna
    if not serial_dev and not ha_dev and not valid_host_name(s["modbus_host"]):
        errors["modbus_host"] = tr("Upišite IP adresu loggera (npr. 192.168.5.199).")
    for key in HA_ENTITY_KEYS:
        s[key] = text(key) if key in form else current[key]
        if s[key] and not _ENTITY.match(s[key]):
            errors[key] = tr("Upišite ID entiteta, npr. sensor.inverter_active_power.")
    if ha_dev and not s["ha_power_entity"] and "ha_power_entity" not in errors:
        errors["ha_power_entity"] = tr("Obavezno polje.")

    s["logger_interface"] = text("logger_interface")
    if s["logger_interface"] and s["logger_interface"] not in interfaces:
        if serial_dev:
            s["logger_interface"] = ""
        else:
            errors["logger_interface"] = tr("Ova mrežna kartica više ne postoji.")
    s["internet_interface"] = text("internet_interface")
    if s["internet_interface"] and s["internet_interface"] not in interfaces:
        errors["internet_interface"] = tr("Ova mrežna kartica više ne postoji.")

    values: dict[str, Any] = {}
    for key, integer, lo, hi in _NUMBERS:
        d = _number(form.get(key, current[key]))
        if d is None or (integer and not float(d).is_integer()):
            errors[key] = tr("Upišite cijeli broj.") if integer else tr("Upišite broj.")
        elif d < lo or d > hi:
            errors[key] = tr("Dopušteno od {lo} do {hi}.", {"lo": _fmt_bound(lo), "hi": _fmt_bound(hi)})
        else:
            values[key] = int(d) if integer else d

    for key, lo, hi in _TEXTS:
        value = text(key)
        if not lo <= len(value) <= hi:
            errors[key] = tr("Obavezno polje.") if not value else tr("Najviše {n} znakova.", {"n": hi})
        s[key] = value

    for key in _BOOLS:
        values[key] = bool(form[key]) if key in form and isinstance(form[key], bool) else current[key]

    theme = form.get("theme", current["theme"])
    scale = form.get("display_scale", current["display_scale"])
    lang = form.get("language", current["language"])
    if theme not in THEMES:
        errors["theme"] = tr("Nepoznata tema.")
    if scale not in SCALES:
        errors["display_scale"] = tr("Nepoznata razlučivost.")
    if not i18n.is_language(lang):
        errors["language"] = tr("Nepoznat jezik.")
    if device not in DEVICE_TYPES:
        errors["device_type"] = tr("Nepoznat uređaj.")
    units = str(form.get("inverter_units", current["inverter_units"])).replace(" ", "")
    try:
        forecast_days = int(form.get("forecast_days", current["forecast_days"]))
    except (TypeError, ValueError):
        forecast_days = 0
    if forecast_days not in (2, 3, 5):
        errors["forecast_days"] = tr("Izaberite 2, 3 ili 5 dana.")
    city = str(form.get("weather_city", current["weather_city"])).strip()[:120]
    palette = form.get("palette", current["palette"])
    if palette in ("dark", "light"):
        palette = ""
    if palette not in PALETTES:
        errors["palette"] = tr("Nepoznata tema.")
    icon_theme = form.get("icon_theme", current["icon_theme"])
    if icon_theme not in ICON_THEMES:
        errors["icon_theme"] = tr("Nepoznata tema ikona.")
    design = form.get("design", current["design"])
    if design not in DESIGNS:
        errors["design"] = tr("Nepoznat izgled.")
    serial = str(form.get("logger_serial", current["logger_serial"])).strip()
    if device == "vendor":
        vp = find_vendor(profile)
        if not vp:
            errors["device_profile"] = tr("Odaberite proizvođača i model invertera.")
        port = values.get("modbus_port", current["modbus_port"])
        if vp and vp.link == "solarman" and port == 8899 and not parse_logger_serial(serial):
            errors["logger_serial"] = tr("Upišite serijski broj Wi-Fi loggera (10 znamenki, s naljepnice na loggeru).")
    if device in ("inverter", "sunspec", "vendor") and not parse_units(units):
        errors["inverter_units"] = tr("Upišite adrese invertera odvojene zarezom, npr. 1 ili 1,2,3 (0–247, najviše 10).")

    s["night_mode"] = form.get("night_mode", current["night_mode"])
    if s["night_mode"] not in NIGHT_MODES:
        errors["night_mode"] = tr("Nepoznat noćni način.")
    for key in ("night_from", "night_to"):
        s[key] = text(key) if key in form else s[key]
        if not _TIME.match(s[key]):
            errors[key] = tr("Upišite vrijeme kao SS:MM, npr. 22:00.")
    s["smtp_security"] = form.get("smtp_security", current["smtp_security"])
    if s["smtp_security"] not in SMTP_SECURITY:
        errors["smtp_security"] = tr("Nepoznata zaštita veze.")
    emails, bad = parse_recipients(text("alert_emails") if "alert_emails" in form else current["alert_emails"])
    if emails is None:
        errors["alert_emails"] = (tr("Najviše {n} adresa.", {"n": MAX_RECIPIENTS}) if not bad
                                  else tr("Neispravna adresa e-pošte: {address}", {"address": bad}))
    s["alert_emails"] = ", ".join(emails or [])
    s["mail_provider"] = form.get("mail_provider", current["mail_provider"])
    if s["mail_provider"] not in MAIL_PROVIDERS:
        errors["mail_provider"] = tr("Nepoznat način slanja e-pošte.")
    key = str(form.get("resend_api_key") or "").strip()
    if key:
        if valid_resend_key(key):
            s["resend_api_key_enc"] = key
        else:
            errors["resend_api_key"] = tr("API ključ servisa Resend nije ispravan (počinje s re_).")
    if form.get("resend_api_key_clear"):
        s["resend_api_key_enc"] = ""
    if s["mail_provider"] == "resend":
        if s["alert_emails"] and not s["resend_api_key_enc"] and "resend_api_key" not in errors:
            errors["resend_api_key"] = tr("Upišite API ključ servisa Resend.")
    elif s["alert_emails"] and not s["smtp_host"]:
        errors["smtp_host"] = tr("Obavezno polje.")
    if s["smtp_host"] and not valid_host_name(s["smtp_host"]):
        errors["smtp_host"] = tr("Upišite naziv ili IP adresu poslužitelja e-pošte.")
    if s["smtp_from"] and not parse_recipients(s["smtp_from"])[0]:
        errors["smtp_from"] = tr("Neispravna adresa e-pošte: {address}", {"address": s["smtp_from"]})
    pwd = form.get("smtp_password") or ""
    if isinstance(pwd, str) and pwd:
        s["smtp_password_enc"] = pwd
    elif (s["smtp_host"] != current["smtp_host"] or s["smtp_user"] != current["smtp_user"]
          or s["smtp_security"] != current["smtp_security"] or values.get("smtp_port", current["smtp_port"]) != current["smtp_port"]):
        s["smtp_password_enc"] = ""  # NEW-03: spremljena lozinka ne prelazi na drugi poslužitelj ili račun
    if not s["smtp_user"]:
        s["smtp_password_enc"] = ""

    if errors:
        return None, errors
    s.update(values)
    s.update({"theme": theme, "display_scale": scale, "language": lang, "device_type": device,
              "inverter_units": units or "1", "device_profile": profile, "palette": palette, "icon_theme": icon_theme,
              "design": design, "forecast_days": forecast_days, "weather_city": city, "logger_serial": serial})
    return settings_from_json(s), {}


def mail_configured(s: dict[str, Any]) -> bool:
    return bool(s["resend_api_key_enc"]) if s["mail_provider"] == "resend" else bool(s["smtp_host"])
