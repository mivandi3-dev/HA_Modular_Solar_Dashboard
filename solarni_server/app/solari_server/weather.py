"""Vremenska prognoza s Open-Meteo (weather.cpp) – bez API ključa, keš 15 min, zadnja uspješna ostaje pri grešci."""
from __future__ import annotations

import json
import threading
import urllib.parse
from typing import Any

from .i18n import tr
from .netinfo import http_get, source_ip
from .util import log, now

TTL_S = 15 * 60
RETRY_S = 60
TIMEOUT_S = 12

WMO = {0: "Vedro", 1: "Pretežno vedro", 2: "Djelomično oblačno", 3: "Oblačno", 45: "Magla", 48: "Magla s injem",
       51: "Slaba rosulja", 53: "Rosulja", 55: "Jaka rosulja", 56: "Ledena rosulja", 57: "Ledena rosulja", 61: "Slaba kiša",
       63: "Kiša", 65: "Jaka kiša", 66: "Ledena kiša", 67: "Ledena kiša", 71: "Slab snijeg", 73: "Snijeg", 75: "Jak snijeg",
       77: "Zrnati snijeg", 80: "Pljuskovi", 81: "Pljuskovi", 82: "Jaki pljuskovi", 85: "Snježni pljuskovi",
       86: "Snježni pljuskovi", 95: "Grmljavina", 96: "Grmljavina s tučom", 99: "Grmljavina s tučom"}


def weather_label(code: int) -> str:
    return WMO.get(code, "—")


def parse_forecast(raw: dict[str, Any]) -> dict[str, Any]:
    cur, d = raw["current"], raw["daily"]
    days = []
    for i in range(len(d["time"])):
        def at(key: str) -> Any:
            v = d.get(key)
            return v[i] if isinstance(v, list) and i < len(v) else None

        sunshine = at("sunshine_duration")
        days.append({"date": at("time"), "code": at("weather_code"), "tmax": at("temperature_2m_max"),
                     "tmin": at("temperature_2m_min"), "sunrise": at("sunrise"), "sunset": at("sunset"),
                     "radiation_mj": at("shortwave_radiation_sum"), "uv": at("uv_index_max"),
                     "sunshine_h": sunshine / 3600 if isinstance(sunshine, (int, float)) else 0,
                     "rain_pct": at("precipitation_probability_max")})
    hourly = []
    h = raw.get("hourly") or {}
    for t, rad in zip(h.get("time", []), h.get("shortwave_radiation", [])):
        hourly.append([t, float(rad) if isinstance(rad, (int, float)) else 0.0])
    return {"temperature": cur["temperature_2m"], "code": cur["weather_code"], "is_day": cur.get("is_day", 1),
            "wind_kmh": cur["wind_speed_10m"], "radiation_wm2": cur["shortwave_radiation"], "days": days, "hourly": hourly}


def _get_json(url: str, source: str | None) -> Any:
    try:
        status, body = http_get(url, TIMEOUT_S, source)
    except OSError as e:
        raise RuntimeError(str(e)) from e
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    try:
        return json.loads(body)
    except ValueError as e:
        raise RuntimeError(tr("Neočekivan odgovor poslužitelja prognoze")) from e


def fetch(lat: float, lon: float, source: str | None = None) -> dict[str, Any]:
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f"
           "&current=temperature_2m,weather_code,wind_speed_10m,shortwave_radiation,is_day"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,shortwave_radiation_sum,"
           "uv_index_max,sunshine_duration,precipitation_probability_max&hourly=shortwave_radiation"
           "&timezone=auto&forecast_days=6") % (lat, lon)
    try:
        return parse_forecast(_get_json(url, source))
    except (KeyError, TypeError) as e:
        raise RuntimeError(tr("Neočekivan odgovor poslužitelja prognoze")) from e


def parse_geocoding(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for r in raw.get("results") or []:
        lat, lon = r.get("latitude"), r.get("longitude")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        label = r.get("name", "")
        for k in ("admin1", "country"):
            part = r.get(k, "")
            if part and part != label:
                label += ", " + part
        out.append({"label": label, "name": r.get("name", ""), "lat": float(lat), "lon": float(lon)})
    return out


def geocode(name: str, language: str, source: str | None = None) -> list[dict[str, Any]]:
    q = name.strip()[:100]
    if not q:
        return []
    lang = "".join(c for c in language if c.isalpha())[:5] or "en"
    url = ("https://geocoding-api.open-meteo.com/v1/search?name=" + urllib.parse.quote(q, safe="")
           + f"&count=8&format=json&language={lang}")
    return parse_geocoding(_get_json(url, source))


class WeatherService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: dict[str, Any] | None = None
        self._at = 0
        self._key = ""

    def get(self, s: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            key = f"{s['weather_lat']},{s['weather_lon']},{s['internet_interface']}"
            t = now()
            if key == self._key and t - self._at < (RETRY_S if self._last is None else TTL_S):
                return self._last
            self._at = t
            try:
                self._last = fetch(s["weather_lat"], s["weather_lon"], source_ip(s["internet_interface"]))
            except RuntimeError as e:
                log.warning("Prognoza: %s", e)
                if key != self._key:
                    self._last = None  # promijenjena lokacija – stara prognoza ne vrijedi
            self._key = key
            return self._last
