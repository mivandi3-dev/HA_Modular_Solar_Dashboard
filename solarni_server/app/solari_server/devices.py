"""Očitanje elektrane (poller.cpp: read_plant, device_capabilities, poll_once)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .i18n import tr
from .modbus import INV_METER_POWER_KW, ModbusClient, ModbusError, Register
from .storage import Db, Reading
from .util import local_date, local_midnight, log, now

INVERTER_TIMEOUT_MS = 10_000  # SDongle i WLAN invertera odgovaraju sporije
INVERTER_CONNECT_DELAY_S = 1.0  # inverter odbija zahtjeve odmah nakon spajanja
MAX_GAP_S = 15 * 60


@dataclass
class PlantReading:
    reading: Reading = field(default_factory=Reading)
    load_kw: float | None = None
    meter_error: str = ""
    device_name: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def huawei_inverter_extras(client: ModbusClient, unit: int) -> dict[str, Any]:
    """SUN2000: temperatura 32087, napon faze A 32069, frekvencija 32085; LUNA2000: SOC 37760, snaga 37765 (> 0 punjenje)."""
    x: dict[str, Any] = {}

    def get(key: str, reg: Register) -> None:
        try:
            x[key] = client.read_value(reg, unit)
        except ModbusError:
            pass

    get("inverter_temp", Register(32087, "I16", 10))
    get("grid_v", Register(32069, "U16", 10))
    get("grid_hz", Register(32085, "U16", 100))
    get("battery_soc", Register(37760, "U16", 10))
    if "battery_soc" in x:
        get("battery_kw", Register(37765, "I32", 1000))
        x["battery_dir"] = True
    return x


def read_plant(s: dict[str, Any]) -> PlantReading:
    from .config import parse_units
    from .fronius import read_fronius
    from .hass_device import read_homeassistant
    from .netinfo import source_ip
    from .offgrid import read_vedirect, read_voltronic
    from .sunspec import read_sunspec
    from .vendors import read_vendor

    readers = {"sunspec": read_sunspec, "fronius": read_fronius, "vendor": read_vendor, "voltronic": read_voltronic,
               "vedirect": read_vedirect, "homeassistant": read_homeassistant}
    if s["device_type"] in readers:
        return readers[s["device_type"]](s)
    inverter = s["device_type"] == "inverter"
    out = PlantReading()
    with ModbusClient(s["modbus_host"], s["modbus_port"], s["modbus_unit_id"], source_ip(s["logger_interface"]) or "",
                      INVERTER_TIMEOUT_MS if inverter else 5000, "Inverter" if inverter else "SmartLogger") as client:
        if inverter:
            units = parse_units(s["inverter_units"])
            if not units:
                raise RuntimeError(tr("Upišite adrese invertera odvojene zarezom, npr. 1 ili 1,2,3 (0–247, najviše 10)."))
            time.sleep(INVERTER_CONNECT_DELAY_S)
            for i, unit in enumerate(units):
                r = client.read_inverter(unit)
                if i == 0:
                    out.extra = huawei_inverter_extras(client, unit)
                    out.reading.pf, out.reading.status = r.pf, r.status
                out.reading.power_kw += r.power_kw
                out.reading.e_daily_kwh += r.e_daily_kwh
                out.reading.e_total_kwh += r.e_total_kwh
        else:
            out.reading = client.read()
        if s["meter_unit_id"]:
            try:  # greška mjerača ne poništava očitanje elektrane
                out.load_kw = (-client.read_value(INV_METER_POWER_KW, s["meter_unit_id"]) if inverter
                               else client.read_meter_kw(s["meter_unit_id"]))
            except ModbusError as e:
                out.meter_error = str(e)
    return out


def device_capabilities(s: dict[str, Any]) -> list[str]:
    from .vendors import find_vendor

    caps: list[str] = []

    def add(*items: str) -> None:
        for c in items:
            if c not in caps:
                caps.append(c)

    t = s["device_type"]
    if t == "inverter":
        add("battery", "temperature", "grid")
    if t == "sunspec":
        add("temperature", "grid")
    if t == "fronius":
        add("battery")
    if t == "voltronic":
        add("battery", "temperature", "grid", "offgrid")
    if t == "vedirect":
        add("battery", "offgrid")
    if t == "homeassistant" and s["ha_battery_soc_entity"]:
        add("battery")
    if t == "vendor":
        p = find_vendor(s["device_profile"])
        for key, _ in p.extras if p else []:
            if key == "battery_soc":
                add("battery")
            if key == "inverter_temp":
                add("temperature")
            if key in ("grid_v", "grid_hz"):
                add("grid")
            if key in ("battery_v", "ac_load_w", "ac_out_v"):
                add("offgrid")
    return caps


def integrate_total(db: Db, t: int, power_kw: float) -> float:
    """Ukupna energija iz snage (uređaji bez brojila): zadnje ukupno + trapez; nakon prekida > 15 min ništa se ne dodaje."""
    last = db.latest()
    if not last:
        return 0.0
    dt = t - last.ts
    if dt <= 0 or dt > MAX_GAP_S:
        return last.e_total_kwh
    return last.e_total_kwh + (last.power_kw + power_kw) / 2.0 * dt / 3600.0


def daily_from_total(db: Db, t: int, e_total_kwh: float) -> float:
    base = db.day_start_total(local_midnight(local_date(t)))
    return max(0.0, e_total_kwh - base) if base is not None else 0.0


def store_reading(db: Db, p: PlantReading, t: int | None = None) -> None:
    """Upis jednog očitanja; dnevnu/ukupnu energiju koju uređaj ne daje računa iz povijesti (poll_once).

    Napomena: Windows poller (poller.cpp, loop) upisuje očitanje bez ovih izračuna i bez podataka uređaja (extra) –
    ovdje se koristi ispravan put iz poll_once, pa SunSpec/Victron/off-grid i widgeti baterije rade u bazi."""
    t = t or now()
    if p.reading.e_total_kwh < 0:
        p.reading.e_total_kwh = integrate_total(db, t, p.reading.power_kw)
    if p.reading.e_daily_kwh < 0:
        p.reading.e_daily_kwh = daily_from_total(db, t, p.reading.e_total_kwh)
    db.insert(t, p.reading, p.load_kw, p.extra)


def poll_once(s: dict[str, Any], db: Db) -> bool:
    try:
        p = read_plant(s)
        if p.meter_error:
            log.warning("Mjerač (unit %s): %s", s["meter_unit_id"], p.meter_error)
        store_reading(db, p)
        return True
    except Exception as e:  # noqa: BLE001 – poller nikad ne smije stati
        log.warning("%s", e)
        return False
