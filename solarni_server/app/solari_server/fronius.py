"""Fronius Solar API (fronius.cpp): GetPowerFlowRealtimeData – Datamanager, GEN24, Symo Hybrid."""
from __future__ import annotations

import json
import urllib.error
from typing import TYPE_CHECKING, Any

from .i18n import tr
from .netinfo import http_get

if TYPE_CHECKING:
    from .devices import PlantReading

TIMEOUT_S = 8
POWER_FLOW_PATH = "/solar_api/v1/GetPowerFlowRealtimeData.fcgi"


def _num(obj: Any, key: str) -> float | None:
    if not isinstance(obj, dict):
        return None
    v = obj.get(key)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _inverters_sum(data: dict[str, Any], key: str) -> float | None:
    inv = data.get("Inverters")
    if not isinstance(inv, dict):
        return None
    total = None
    for item in inv.values():
        v = _num(item, key)
        if v is not None:
            total = (total or 0.0) + v
    return total


def parse_powerflow(body: dict[str, Any], with_meter: bool) -> "PlantReading":
    from .devices import PlantReading

    status = (body.get("Head") or {}).get("Status") or {}
    if status.get("Code", 0) != 0:
        raise RuntimeError(tr("Fronius javlja grešku: {error}", {"error": status.get("Reason") or status.get("Code")}))
    data = (body.get("Body") or {}).get("Data") or {}
    site = data.get("Site")
    if not isinstance(site, dict) or not site:
        raise RuntimeError(tr("Neočekivan odgovor uređaja."))
    out = PlantReading(device_name="Fronius")
    pv = _num(site, "P_PV")  # null noću
    out.reading.power_kw = max(0.0, pv if pv is not None else (_inverters_sum(data, "P") or 0.0)) / 1000.0
    total = _num(site, "E_Total")
    total = total if total is not None else _inverters_sum(data, "E_Total")
    if total is None:
        raise RuntimeError(tr("Fronius ne daje ukupnu proizvedenu energiju."))
    out.reading.e_total_kwh = total / 1000.0
    day = _num(site, "E_Day")
    day = day if day is not None else _inverters_sum(data, "E_Day")
    out.reading.e_daily_kwh = day / 1000.0 if day is not None else -1  # GEN24 bez E_Day – računa poller
    out.reading.pf = 0.0
    out.reading.status = 1 if out.reading.power_kw > 0 else 0
    if with_meter:
        grid = _num(site, "P_Grid")
        if grid is not None:
            out.load_kw = grid / 1000.0  # + iz mreže
        else:
            out.meter_error = tr("Fronius ne javlja snagu mreže (P_Grid) – je li Smart Meter spojen?")
    akku = _num(site, "P_Akku")  # > 0 pražnjenje
    if akku is not None:
        soc = None
        for inv in (data.get("Inverters") or {}).values() if isinstance(data.get("Inverters"), dict) else []:
            v = _num(inv, "SOC")
            if v is not None:
                soc = v
        if soc is not None:
            out.extra.update({"battery_soc": soc, "battery_kw": -akku / 1000.0, "battery_dir": True})
    return out


def read_fronius(s: dict[str, Any]) -> "PlantReading":
    from .netinfo import source_ip

    base = f"http://{s['modbus_host']}" + ("" if s["modbus_port"] == 80 else f":{s['modbus_port']}")
    try:
        status, body = http_get(base + POWER_FLOW_PATH, TIMEOUT_S, source_ip(s["logger_interface"]))
    except (OSError, urllib.error.URLError) as e:
        raise RuntimeError(tr("Fronius ({host}) ne odgovara: {error}", {"host": s["modbus_host"], "error": e})) from e
    if status == 404:
        raise RuntimeError(tr("Uređaj na {host} nema Fronius Solar API.", {"host": s["modbus_host"]}))
    if status != 200:
        raise RuntimeError(tr("Uređaj je vratio grešku {code}.", {"code": status}))
    try:
        return parse_powerflow(json.loads(body), s["meter_unit_id"] != 0)
    except ValueError as e:
        raise RuntimeError(tr("Neočekivan odgovor uređaja.")) from e
