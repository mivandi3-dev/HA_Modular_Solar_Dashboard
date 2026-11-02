"""Inverteri ostalih proizvođača preko Modbusa (vendors.cpp) – iste tablice registara i izvori:
Sungrow, GoodWe, Deye/Sunsynk, Solis, Fox ESS, Growatt, Victron Energy GX te off-grid uređaji na serijskom portu
(Growatt SPF, EPEver, SRNE)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from .i18n import tr
from .modbus import ModbusClient, ModbusError

if TYPE_CHECKING:
    from .devices import PlantReading

TIMEOUT_MS = 8000
MAX_READ, MAX_GAP = 125, 8
SOLARMAN_PORT = 8899


@dataclass(frozen=True)
class Point:
    lo: int
    hi: int = 0
    wide: bool = False
    sign: bool = False
    scale: float = 1.0
    offset: float = 0.0


def u16(a: int, scale: float = 1) -> Point: return Point(a, 0, False, False, scale)
def s16(a: int, scale: float = 1) -> Point: return Point(a, 0, False, True, scale)
def u32(lo: int, hi: int, scale: float = 1) -> Point: return Point(lo, hi, True, False, scale)
def s32(lo: int, hi: int, scale: float = 1) -> Point: return Point(lo, hi, True, True, scale)
def u32be(a: int, scale: float = 1) -> Point: return u32(a + 1, a, scale)  # viša riječ na nižoj adresi
def s32be(a: int, scale: float = 1) -> Point: return s32(a + 1, a, scale)
def temp_deye(a: int) -> Point: return Point(a, 0, False, False, 0.1, 1000)  # (sirovo − 1000) × 0,1 °C
def range16(a: int, b: int) -> list[Point]: return [u16(x) for x in range(a, b + 1)]


@dataclass
class VendorProfile:
    key: str
    name: str
    fc: int
    link: str  # tcp | solarman | goodwe | serial (serial: port = uobičajena brzina)
    port: int
    unit: int
    power: list[Point]
    today: Point | None
    total: Point | None
    meter: list[Point]
    meter_import_positive: bool
    extras: list[tuple[str, Point]] = field(default_factory=list)
    battery_sign: int = 0  # +1: battery_w > 0 punjenje, −1: > 0 pražnjenje, 0: smjer nepoznat


def _make() -> list[VendorProfile]:
    p = [
        VendorProfile("victron", "Victron Energy GX", 3, "tcp", 502, 100, range16(808, 816) + [u16(850)], None, None,
                      [s16(820), s16(821), s16(822)], True),
        VendorProfile("sungrow_sg", "Sungrow SG", 4, "tcp", 502, 1, [u32(5030, 5031)], u16(5002, 0.1), u32(5003, 5004),
                      [s32(5215, 5216)], False),
        VendorProfile("sungrow_sh", "Sungrow SH", 4, "tcp", 502, 1, [u32(5016, 5017)], u16(13001, 0.1), u32(13002, 13003, 0.1),
                      [s32(13009, 13010)], False),
        VendorProfile("goodwe_et", "GoodWe ET / EH / BT", 3, "goodwe", 8899, 0xF7,
                      [u32be(35105), u32be(35109), u32be(35113), u32be(35117)], u32be(35193, 0.1), u32be(35191, 0.1),
                      [s16(35140)], False),
        VendorProfile("goodwe_dt", "GoodWe DT / SDT / SMT", 3, "goodwe", 8899, 0x7F, [u32be(30127)], u16(30144, 0.1),
                      u32be(30145, 0.1), [s32be(30195)], False),
        VendorProfile("deye_string", "Deye SUN-K-G", 3, "solarman", 8899, 1, [u32(0x56, 0x57, 0.1)], u16(0x3C, 0.1),
                      u32(0x3F, 0x40, 0.1), [s32(0xCB, 0xCC)], True),
        VendorProfile("deye_hybrid", "Deye / Sunsynk SG01LP1 (1~)", 3, "solarman", 8899, 1, range16(0xBA, 0xBD),
                      u16(0x6C, 0.1), u32(0x60, 0x61, 0.1), [s16(0xA9)], True),
        VendorProfile("deye_hybrid3", "Deye / Sunsynk SG04LP3 / HP3 (3~)", 3, "solarman", 8899, 1, range16(0x2A0, 0x2A3),
                      None, u32(0x216, 0x217, 0.1), [s32(0x271, 0x2B2)], True),
        VendorProfile("solis_string", "Solis 4G / 5G", 4, "tcp", 502, 1, [u32be(3006)], u16(3014, 0.1), u32be(3008), [], False),
        VendorProfile("solis_hybrid", "Solis RHI / S6 hybrid", 4, "tcp", 502, 1, [u32be(33057)], u16(33035, 0.1),
                      u32be(33029), [s32be(33263)], False),
        VendorProfile("foxess", "Fox ESS H1 / H3", 3, "tcp", 502, 247, [s16(31002), s16(31005)], u16(32002, 0.1),
                      u32be(32000, 0.1), [s16(31014)], False),
        VendorProfile("growatt", "Growatt (MIC / MIN / MOD / MAX)", 4, "tcp", 502, 1, [u32be(35, 0.1)], u32be(53, 0.1),
                      u32be(55, 0.1), [], False),
        # off-grid sustavi preko serijskog porta – NISU isprobani na stvarnim uređajima
        VendorProfile("growatt_spf", "Growatt SPF (off-grid)", 4, "serial", 9600, 1, [u32be(3, 0.1)], u32be(48, 0.1),
                      u32be(50, 0.1), [], False),
        VendorProfile("epever", "EPEver Tracer / UPower", 4, "serial", 115200, 1, [u32(0x3102, 0x3103, 0.01)],
                      u32(0x330C, 0x330D, 0.01), u32(0x3312, 0x3313, 0.01), [], False),
        VendorProfile("srne", "SRNE (HF / ML / ASF)", 3, "serial", 9600, 1, [u16(0x0109), u16(0x0111)], u16(0xF02F, 0.1),
                      u32(0xF038, 0xF039, 0.1), [], False),
    ]
    extras: dict[str, tuple[list[tuple[str, Point]], int]] = {
        "victron": ([("battery_soc", u16(843)), ("battery_w", s16(842)), ("battery_v", u16(840, 0.1)),
                     ("ac_load_w", u16(817)), ("ac_load_w", u16(818)), ("ac_load_w", u16(819))], +1),
        "growatt_spf": ([("battery_soc", u16(18)), ("battery_w", s32be(77, 0.1)), ("battery_v", u16(17, 0.01)),
                         ("inverter_temp", u16(25, 0.1)), ("grid_v", u16(20, 0.1)), ("grid_hz", u16(21, 0.01)),
                         ("ac_out_v", u16(22, 0.1)), ("ac_out_hz", u16(23, 0.01)), ("ac_load_w", u32be(9, 0.1)),
                         ("load_pct", u16(27, 0.1))], -1),
        "epever": ([("battery_soc", u16(0x311A)), ("battery_v", u16(0x331A, 0.01)), ("battery_a", s32(0x331B, 0x331C, 0.01)),
                    ("inverter_temp", s16(0x3111, 0.01)), ("ac_load_w", u32(0x310E, 0x310F, 0.01))], +1),
        "srne": ([("battery_soc", u16(0x0100)), ("battery_v", u16(0x0101, 0.1)), ("battery_a", s16(0x0102, 0.1)),
                  ("inverter_temp", u16(0x0220, 0.1)), ("grid_v", u16(0x0213, 0.1)), ("grid_hz", u16(0x0215, 0.01)),
                  ("ac_load_w", u16(0x021B))], +1),
        "sungrow_sg": ([("inverter_temp", s16(5007, 0.1)), ("grid_v", u16(5018, 0.1)), ("grid_hz", u16(5035, 0.1))], 0),
        "sungrow_sh": ([("inverter_temp", s16(5007, 0.1)), ("grid_v", u16(5018, 0.1)), ("grid_hz", u16(5035, 0.1)),
                        ("battery_soc", u16(13022, 0.1)), ("battery_w", s16(13021))], 0),
        "goodwe_et": ([("inverter_temp", s16(35176, 0.1)), ("grid_v", u16(35121, 0.1)), ("grid_hz", u16(35123, 0.01)),
                       ("battery_soc", u16(37007)), ("battery_w", s32be(35182))], -1),
        "deye_string": ([("inverter_temp", temp_deye(0x5B)), ("grid_v", u16(0x49, 0.1)), ("grid_hz", u16(0x4F, 0.01))], 0),
        "deye_hybrid": ([("inverter_temp", temp_deye(0x5B)), ("grid_v", u16(0x96, 0.1)), ("grid_hz", u16(0x4F, 0.01)),
                         ("battery_soc", u16(0xB8)), ("battery_w", s16(0xBE))], -1),
        "deye_hybrid3": ([("inverter_temp", temp_deye(0x21D)), ("grid_v", u16(0x256, 0.1)), ("grid_hz", u16(0x261, 0.01)),
                          ("battery_soc", u16(0x24C)), ("battery_w", s16(0x24E))], -1),
        "solis_string": ([("inverter_temp", s16(3041, 0.1))], 0),
        "solis_hybrid": ([("inverter_temp", s16(33093, 0.1)), ("battery_soc", u16(33139)), ("battery_w", s32be(33149))], 0),
        "growatt": ([("inverter_temp", u16(93, 0.1)), ("grid_v", u16(38, 0.1)), ("grid_hz", u16(37, 0.01))], 0),
    }
    for prof in p:
        if prof.key in extras:
            prof.extras, prof.battery_sign = extras[prof.key]
    return p


PROFILES = _make()


def find_vendor(key: str) -> VendorProfile | None:
    return next((p for p in PROFILES if p.key == key), None)


Regs = dict[int, int]


def vendor_value(p: Point, regs: Regs) -> float:
    def word(a: int) -> int:
        if a not in regs:
            raise ModbusError(tr("Neočekivan odgovor uređaja."))
        return regs[a]

    if not p.wide:
        w = word(p.lo)
        raw = w - 0x10000 if p.sign and w & 0x8000 else w
    else:
        v = (word(p.hi) << 16) | word(p.lo)
        raw = v - (1 << 32) if p.sign and v & 0x80000000 else v
    return (raw - p.offset) * p.scale


def vendor_ranges(addresses: list[int]) -> list[tuple[int, int]]:
    """Najmanji broj čitanja: susjedne adrese u jednom zahtjevu (do 125 registara, rupe do 8 registara se čitaju)."""
    out: list[list[int]] = []
    for addr in sorted(set(addresses)):
        if out:
            start, count = out[-1]
            end = start + count
            if addr < end:
                continue
            if addr - end <= MAX_GAP and addr - start + 1 <= MAX_READ:
                out[-1][1] = addr - start + 1
                continue
        out.append([addr, 1])
    return [(a, c) for a, c in out]


def _collect(points: list[Point]) -> list[int]:
    out: list[int] = []
    for p in points:
        out.append(p.lo)
        if p.wide:
            out.append(p.hi)
    return out


def read_extras(prof: VendorProfile, read: Callable[[list[Point]], Regs]) -> dict[str, Any]:
    x: dict[str, Any] = {}
    if not prof.extras:
        return x
    battery_a = math.nan

    def store(key: str, v: float) -> None:
        nonlocal battery_a
        if key == "battery_w":
            x["battery_kw"] = (-v if prof.battery_sign < 0 else v) / 1000.0
            x["battery_dir"] = prof.battery_sign != 0
        elif key == "battery_a":
            battery_a = v
        elif key == "ac_load_w":  # po fazama se zbraja
            x["ac_load_kw"] = x.get("ac_load_kw", 0.0) + v / 1000.0
        else:
            x[key] = v

    try:
        regs = read([pt for _, pt in prof.extras])
        for key, pt in prof.extras:
            store(key, vendor_value(pt, regs))
    except ModbusError:  # npr. hibrid bez baterije – adrese se čitaju pojedinačno i preskaču
        x.clear()
        battery_a = math.nan
        for key, pt in prof.extras:
            try:
                store(key, vendor_value(pt, read([pt])))
            except ModbusError:
                pass
    if "battery_kw" not in x and not math.isnan(battery_a) and "battery_v" in x:
        w = x["battery_v"] * battery_a
        x["battery_kw"] = (-w if prof.battery_sign < 0 else w) / 1000.0
        x["battery_dir"] = prof.battery_sign != 0
    if "battery_soc" not in x:
        x.pop("battery_kw", None)
        x.pop("battery_dir", None)
    return x


def read_vendor(s: dict[str, Any]) -> "PlantReading":
    from .config import is_serial_port_name, parse_logger_serial, parse_units
    from .devices import PlantReading
    from .netinfo import source_ip
    from .serialio import SerialPort, rtu_serial_read

    prof = find_vendor(s["device_profile"])
    if not prof:
        raise RuntimeError(tr("Odaberite proizvođača i model invertera."))
    units = parse_units(s["inverter_units"])
    if not units:
        raise RuntimeError(tr("Upišite adrese invertera odvojene zarezom, npr. 1 ili 1,2,3 (0–247, najviše 10)."))
    com = None
    client = None
    if prof.link == "serial":
        if not is_serial_port_name(s["serial_port"]):
            raise RuntimeError(tr("Izaberite serijski port (npr. COM3) ili USB."))
        com = SerialPort(s["serial_port"], s["serial_baud"] or prof.port, 2000)
    try:
        if not com:
            framing, serial = "tcp", 0
            if s["modbus_port"] == SOLARMAN_PORT and prof.link == "solarman":
                sn = parse_logger_serial(s["logger_serial"])
                if not sn:
                    raise RuntimeError(tr("Upišite serijski broj Wi-Fi loggera (10 znamenki, s naljepnice na loggeru)."))
                framing, serial = "solarman", sn
            elif s["modbus_port"] == SOLARMAN_PORT and prof.link == "goodwe":
                framing = "goodwe"
            client = ModbusClient(s["modbus_host"], s["modbus_port"], units[0], source_ip(s["logger_interface"]) or "",
                                  TIMEOUT_MS, prof.name, framing, serial)
            client.connect()

        def read_points(unit: int, points: list[Point]) -> Regs:
            regs: Regs = {}
            for start, count in vendor_ranges(_collect(points)):
                words = (rtu_serial_read(com, unit, prof.fc, start, count) if com
                         else client.read_registers(start, count, unit, prof.fc))  # type: ignore[union-attr]
                for i in range(count):
                    regs[start + i] = words[i]
            return regs

        out = PlantReading(device_name=prof.name)
        today = total = 0.0
        for unit in units:
            pts = list(prof.power) + [p for p in (prof.today, prof.total) if p]
            regs = read_points(unit, pts)
            out.reading.power_kw += max(0.0, sum(vendor_value(p, regs) for p in prof.power)) / 1000.0
            if prof.today:
                today += vendor_value(prof.today, regs)
            if prof.total:
                total += vendor_value(prof.total, regs)
        out.reading.e_daily_kwh = today if prof.today else -1  # bez dnevne – računa poller
        out.reading.e_total_kwh = total if prof.total else -1  # bez ukupne (Victron) – poller integrira snagu
        out.reading.status = 1 if out.reading.power_kw > 0 else 0
        out.extra = read_extras(prof, lambda pts: read_points(units[0], pts))
        if s["meter_unit_id"] and prof.meter:
            try:  # greška mjerača ne poništava očitanje elektrane
                w = sum(vendor_value(p, read_points(units[0], prof.meter)) for p in prof.meter)
                import_positive = prof.meter_import_positive != s["meter_invert"]
                out.load_kw = (w if import_positive else -w) / 1000.0  # load_kw: pozitivno = uzimanje iz mreže
            except ModbusError as e:
                out.meter_error = str(e)
        return out
    finally:
        if com:
            com.close()
        if client:
            client.close()


def profiles_json() -> list[dict[str, Any]]:
    return [{"key": p.key, "name": p.name, "port": p.port, "unit": p.unit, "link": p.link, "meter": bool(p.meter),
             "energy": p.total is not None} for p in PROFILES]
