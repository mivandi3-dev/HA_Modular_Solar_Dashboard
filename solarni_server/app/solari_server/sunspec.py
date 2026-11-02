"""SunSpec Modbus (sunspec.cpp) – SMA, Fronius, SolarEdge, Kostal, ABB/FIMER, Delta…
Oznaka "SunS" na 40000, 0 ili 50000; inverter 101–103 (int + SF) ili 111–113 (float32); mjerač 201–204 ili 211–214."""
from __future__ import annotations

import math
import struct
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from .i18n import tr
from .modbus import ModbusClient, ModbusError
from .storage import Reading

if TYPE_CHECKING:
    from .devices import PlantReading

MARKER = (0x5375, 0x6E53)
BASES = (40000, 0, 50000)
MAX_MODELS = 64
MAX_READ = 125
TIMEOUT_MS = 8000
NOT_I16, NOT_U16 = 0x8000, 0xFFFF


@dataclass(frozen=True)
class Model:
    id: int
    length: int
    address: int


Reader = Callable[[int, int], list[int]]


def _i16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def scaled(value: int, sf_raw: int) -> float:
    if value == NOT_I16 or sf_raw == NOT_I16:
        return 0.0
    return _i16(value) * 10.0 ** _i16(sf_raw)


def scaled_u32(value: int, sf_raw: int) -> float:
    if value == 0 or sf_raw == NOT_I16:
        return 0.0
    return value * 10.0 ** _i16(sf_raw)


def f32(d: list[int], at: int) -> float:
    v = struct.unpack(">f", struct.pack(">HH", d[at], d[at + 1]))[0]
    return v if math.isfinite(v) else 0.0


def u32(d: list[int], at: int) -> int:
    return (d[at] << 16) | d[at + 1]


def power_factor(pf: float) -> float:
    return pf / 100.0 if abs(pf) > 1.5 else pf  # SunSpec daje postotke; neki uređaji -1…1


def read_block(read: Reader, address: int, count: int) -> list[int]:
    out: list[int] = []
    while count > 0:
        n = min(count, MAX_READ)
        out += read(address, n)
        address += n
        count -= n
    return out


def discover(read: Reader) -> list[Model]:
    for base in BASES:
        try:
            marker = read(base, 2)
        except ModbusError:
            continue
        if tuple(marker[:2]) != MARKER:
            continue
        models: list[Model] = []
        at = base + 2
        for _ in range(MAX_MODELS):
            if at + 2 > 0xFFFF:
                break
            head = read(at, 2)
            if len(head) < 2 or head[0] in (0xFFFF, 0):
                break
            models.append(Model(head[0], head[1], at + 2))
            at += 2 + head[1]
        return models
    return []


def find(models: list[Model], lo: int, hi: int) -> Model | None:
    return next((m for m in models if lo <= m.id <= hi), None)


def inverter(model_id: int, d: list[int]) -> Reading:
    r = Reading(e_daily_kwh=-1)
    if 101 <= model_id <= 103:
        if len(d) < 37:
            raise ModbusError(tr("Neočekivan odgovor uređaja."))
        r.power_kw = scaled(d[12], d[13]) / 1000.0
        r.pf = power_factor(scaled(d[20], d[21]))
        r.e_total_kwh = scaled_u32(u32(d, 22), d[24]) / 1000.0
        r.status = 0 if d[36] == NOT_U16 else d[36]
    elif 111 <= model_id <= 113:
        if len(d) < 47:
            raise ModbusError(tr("Neočekivan odgovor uređaja."))
        r.power_kw = f32(d, 20) / 1000.0
        r.pf = power_factor(f32(d, 28))
        r.e_total_kwh = f32(d, 30) / 1000.0
        r.status = 0 if d[46] == NOT_U16 else d[46]
    else:
        raise ModbusError(tr("Uređaj nema SunSpec model invertera."))
    r.power_kw = max(r.power_kw, 0.0)  # noću mala negativna snaga (vlastita potrošnja)
    return r


def extras(model_id: int, d: list[int]) -> dict[str, Any]:
    x: dict[str, Any] = {}

    def put(key: str, v: float, ok: bool) -> None:
        if ok and math.isfinite(v) and v != 0:
            x[key] = v

    if 101 <= model_id <= 103 and len(d) >= 37:
        put("grid_v", scaled(d[8], d[11]), d[8] not in (NOT_U16, NOT_I16))
        put("grid_hz", scaled(d[14], d[15]), d[14] not in (NOT_U16, NOT_I16))
        put("inverter_temp", scaled(d[31], d[35]), d[31] != NOT_I16)
    elif 111 <= model_id <= 113 and len(d) >= 47:
        put("grid_v", f32(d, 14), True)
        put("grid_hz", f32(d, 22), True)
        put("inverter_temp", f32(d, 38), True)
    return x


def meter_w(model_id: int, d: list[int]) -> float | None:
    if 201 <= model_id <= 204:
        if len(d) < 21 or d[16] == NOT_I16:
            return None
        return scaled(d[16], d[20])
    if 211 <= model_id <= 214:
        return f32(d, 26) if len(d) >= 28 else None
    return None


def common_name(d: list[int]) -> str:
    def text(at: int, words: int) -> str:
        s = ""
        for w in d[at:at + words]:
            for c in (w >> 8, w & 0xFF):
                if 32 <= c < 127:
                    s += chr(c)
        return s.rstrip(" ")

    mn, md = text(0, 16), text(16, 16)
    return mn if not md else md if not mn else f"{mn} {md}"


_cache: dict[str, list[Model]] = {}
_cache_lock = threading.Lock()


def _models(client: ModbusClient, key: str, unit: int) -> list[Model]:
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    models = discover(lambda a, n: client.read_registers(a, n, unit))
    if models:
        with _cache_lock:
            _cache[key] = models
    return models


def _forget(key: str) -> None:
    with _cache_lock:
        _cache.pop(key, None)


def read_sunspec(s: dict[str, Any]) -> "PlantReading":
    from .config import parse_units
    from .devices import PlantReading
    from .netinfo import source_ip

    units = parse_units(s["inverter_units"])
    if not units:
        raise RuntimeError(tr("Upišite adrese invertera odvojene zarezom, npr. 1 ili 1,2,3 (0–247, najviše 10)."))
    base = f"{s['modbus_host']}:{s['modbus_port']}/"
    out = PlantReading()
    with ModbusClient(s["modbus_host"], s["modbus_port"], units[0], source_ip(s["logger_interface"]) or "", TIMEOUT_MS,
                      "SunSpec") as client:
        for i, unit in enumerate(units):
            key = base + str(unit)
            try:
                models = _models(client, key, unit)
                if not models:
                    raise ModbusError(tr("Na adresi {unit} nema SunSpec podataka – uključite SunSpec Modbus na uređaju.",
                                         {"unit": unit}))
                inv = find(models, 101, 113)
                if not inv or 103 < inv.id < 111:
                    raise ModbusError(tr("Uređaj nema SunSpec model invertera."))
                data = read_block(lambda a, n: client.read_registers(a, n, unit), inv.address, inv.length)
                r = inverter(inv.id, data)
                if i == 0:
                    out.extra = extras(inv.id, data)
                    out.reading.pf, out.reading.status = r.pf, r.status
                    common = find(models, 1, 1)
                    if common:
                        out.device_name = common_name(read_block(lambda a, n: client.read_registers(a, n, unit),
                                                                 common.address, min(common.length, 32)))
                out.reading.power_kw += r.power_kw
                out.reading.e_total_kwh += r.e_total_kwh
            except ModbusError:
                _forget(key)  # npr. promijenjen firmware – sljedeći put iznova
                raise
        out.reading.e_daily_kwh = -1
        if s["meter_unit_id"]:
            key = base + str(s["meter_unit_id"])
            try:
                models = _models(client, key, s["meter_unit_id"])
                meter = find(models, 201, 214)
                if not meter or 204 < meter.id < 211:
                    raise ModbusError(tr("Na toj adresi nema SunSpec mjerača."))
                w = meter_w(meter.id, read_block(lambda a, n: client.read_registers(a, n, s["meter_unit_id"]),
                                                 meter.address, meter.length))
                if w is None:
                    raise ModbusError(tr("Mjerač ne daje ukupnu snagu."))
                out.load_kw = (-w if s["meter_export_positive"] else w) / 1000.0
            except ModbusError as e:
                _forget(key)
                out.meter_error = str(e)
    return out
