"""Off-grid sustavi (offgrid.cpp):
  * Voltronic Power (Axpert, MPP Solar PIP, EASUN, PowMr, Mecer, Anern, Must PV18…): ASCII protokol QPIGS, 2400 8N1,
    RS232/USB-serijski kabel ili USB HID (0665:5161);
  * Victron VE.Direct (MPPT, Phoenix 12/24/48 V, SmartShunt, BMV): tekstualni protokol 19200 8N1, više uređaja = više portova.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .i18n import tr
from .serialio import SerialError, SerialPort, voltronic_hid_query
from .util import log

if TYPE_CHECKING:
    from .devices import PlantReading

VOLTRONIC_BAUD, VEDIRECT_BAUD = 2400, 19200
VE_LISTEN_MS = 2500


def split_ports(text: str) -> list[str]:
    from .config import normalize_port

    return [normalize_port(p) for p in re.split(r"[,; ]+", text or "") if p]


def nominal_system_voltage(v: float) -> int:
    if not v > 8:
        return 0
    if v < 17:
        return 12
    if v < 34:
        return 24
    if v < 68:
        return 48
    return 0


# ---------------------------------------------------------------- Voltronic
def voltronic_crc(data: bytes) -> int:
    crc = 0
    for c in data:
        crc ^= c << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    hi, lo = crc >> 8, crc & 0xFF
    hi += 1 if hi in (0x28, 0x0D, 0x0A) else 0  # bajtovi koje protokol ne smije poslati
    lo += 1 if lo in (0x28, 0x0D, 0x0A) else 0
    return (hi << 8) | lo


def voltronic_frame(command: str) -> bytes:
    data = command.encode("ascii")
    crc = voltronic_crc(data)
    return data + bytes([crc >> 8, crc & 0xFF]) + b"\r"


def voltronic_unwrap(raw: bytes) -> str:
    start = raw.find(b"(")
    end = raw.find(b"\r", start if start >= 0 else 0)
    if start < 0 or end < 0 or end < start + 3:
        raise SerialError(tr("Izmjenjivač nije odgovorio."))
    body = raw[start:end - 2]
    crc = (raw[end - 2] << 8) | raw[end - 1]
    if voltronic_crc(body) != crc:
        raise SerialError(tr("Odgovor izmjenjivača je oštećen (CRC)."))
    if body.startswith(b"(NAK"):
        raise SerialError(tr("Izmjenjivač ne podržava upit."))
    return body[1:].decode("ascii", "replace")


@dataclass
class VoltronicStatus:
    grid_v: float = 0
    grid_hz: float = 0
    out_v: float = 0
    out_hz: float = 0
    out_va: float = 0
    out_w: float = 0
    load_pct: float = 0
    battery_v: float = 0
    charge_a: float = 0
    battery_pct: float = 0
    heatsink_c: float = 0
    pv_a: float = 0
    pv_v: float = 0
    discharge_a: float = 0
    pv_w: float = 0


def parse_qpigs(fields: str) -> VoltronicStatus | None:
    f = fields.split()
    if len(f) < 16:
        return None

    def d(i: int) -> float:
        try:
            return float(f[i]) if i < len(f) else 0.0
        except ValueError:
            return 0.0

    s = VoltronicStatus(d(0), d(1), d(2), d(3), d(4), d(5), d(6), d(8), d(9), d(10), d(11), d(12), d(13), d(15))
    s.pv_w = d(19) if len(f) > 19 else s.pv_a * s.pv_v  # novije verzije: snaga punjenja iz PV-a (W)
    return s


def read_voltronic(s: dict[str, Any]) -> "PlantReading":
    from .devices import PlantReading

    if not s["serial_port"] or s["serial_port"] == "USB":
        fields = voltronic_hid_query("QPIGS")
    else:
        with SerialPort(s["serial_port"], s["serial_baud"] or VOLTRONIC_BAUD, 3000) as port:
            port.write(voltronic_frame("QPIGS"))
            fields = voltronic_unwrap(port.read_until(3000, lambda r, _: b"\r" in r))
    st = parse_qpigs(fields)
    if not st:
        raise SerialError(tr("Neočekivan odgovor izmjenjivača."))
    out = PlantReading(device_name="Voltronic")
    out.reading.power_kw = max(0.0, st.pv_w) / 1000.0
    out.reading.e_daily_kwh = -1  # energiju poller računa iz snage
    out.reading.e_total_kwh = -1
    out.reading.status = 1 if out.reading.power_kw > 0 else 0
    out.extra = {"battery_soc": st.battery_pct, "battery_v": st.battery_v,
                 "battery_kw": st.battery_v * (st.charge_a - st.discharge_a) / 1000.0, "battery_dir": True,
                 "inverter_temp": st.heatsink_c, "ac_load_kw": st.out_w / 1000.0, "ac_out_v": st.out_v,
                 "ac_out_hz": st.out_hz, "load_pct": st.load_pct}
    if st.grid_v > 50:  # bez mreže polja su 0
        out.extra.update({"grid_v": st.grid_v, "grid_hz": st.grid_hz})
    return out


# ---------------------------------------------------------------- Victron VE.Direct
def parse_vedirect(stream: bytes) -> list[dict[str, str]]:
    """Samo blokovi s ispravnim kontrolnim zbrojem (zbroj svih bajtova bloka mod 256 = 0)."""
    out: list[dict[str, str]] = []
    pos = 0
    while True:
        start = stream.find(b"\r\n", pos)
        if start < 0:
            break
        ck = stream.find(b"\r\nChecksum\t", start)
        if ck < 0 or ck + 12 > len(stream):
            break
        end = ck + 12
        block = stream[start:end]
        if sum(block) & 0xFF == 0:
            b: dict[str, str] = {}
            for line in block[2:ck - start].decode("latin-1").split("\n"):
                line = line.rstrip("\r")
                if "\t" in line and not line.startswith(":"):
                    k, v = line.split("\t", 1)
                    b[k] = v
            if b:
                out.append(b)
        pos = end
    return out


def _num(b: dict[str, str], key: str, scale: float) -> float:
    try:
        return float(b[key]) * scale
    except (KeyError, ValueError):
        return math.nan


@dataclass
class VeSummary:
    pv_w: float = 0
    today_kwh: float = 0
    total_kwh: float = 0
    has_yield: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def summarize_vedirect(blocks: list[dict[str, str]]) -> VeSummary:
    s = VeSummary()
    devices: dict[str, dict[str, str]] = {}
    for b in blocks:  # isti uređaj šalje više blokova – zadnja vrijednost po SER# ili PID-u
        key = b.get("SER#") or b.get("PID") or "?"
        devices.setdefault(key, {}).update(b)
    battery_v = soc = shunt_w = ac_v = math.nan
    mppt_charge_w = ac_va = 0.0
    any_ac = False
    for d in devices.values():
        ppv = _num(d, "PPV", 1)
        if not math.isnan(ppv):  # MPPT punjač
            s.pv_w += ppv
            h20, h19 = _num(d, "H20", 0.01), _num(d, "H19", 0.01)
            if not math.isnan(h20):
                s.today_kwh += h20
                s.has_yield = True
            if not math.isnan(h19):
                s.total_kwh += h19
            v, i = _num(d, "V", 0.001), _num(d, "I", 0.001)
            if not math.isnan(v) and not math.isnan(i):
                mppt_charge_w += v * i
            if math.isnan(battery_v) and not math.isnan(v):
                battery_v = v
        soc_pm = _num(d, "SOC", 0.1)  # SmartShunt / BMV: promili
        if not math.isnan(soc_pm):
            soc = soc_pm
            v, p = _num(d, "V", 0.001), _num(d, "P", 1)
            if not math.isnan(v):
                battery_v = v
            if not math.isnan(p):
                shunt_w = p
        va = _num(d, "AC_OUT_S", 1)  # Phoenix izmjenjivač
        if not math.isnan(va):
            ac_va += va
            any_ac = True
            v = _num(d, "AC_OUT_V", 0.01)
            if not math.isnan(v):
                ac_v = v
    if not math.isnan(battery_v):
        s.extra["battery_v"] = battery_v
    if not math.isnan(soc):
        s.extra.update({"battery_soc": soc, "battery_kw": (mppt_charge_w if math.isnan(shunt_w) else shunt_w) / 1000.0,
                        "battery_dir": True})
    if any_ac:
        s.extra["ac_load_kw"] = ac_va / 1000.0
        if not math.isnan(ac_v):
            s.extra["ac_out_v"] = ac_v
    return s


def read_vedirect(s: dict[str, Any]) -> "PlantReading":
    from .devices import PlantReading

    ports = split_ports(s["serial_port"])
    if not ports:
        raise SerialError(tr("Upišite COM port VE.Direct kabela, npr. COM3 (više uređaja: COM3, COM4)."))
    blocks: list[dict[str, str]] = []
    errors: list[str] = []
    for p in ports:
        try:
            with SerialPort(p, VEDIRECT_BAUD, 500) as port:
                got = parse_vedirect(port.read_until(VE_LISTEN_MS, None))
            if not got:
                errors.append(tr("{port}: nema podataka", {"port": p}))
            blocks += got
        except SerialError as e:
            errors.append(str(e))
    if not blocks:
        raise SerialError("; ".join(errors) if errors else tr("VE.Direct uređaj ne šalje podatke."))
    summary = summarize_vedirect(blocks)
    out = PlantReading(device_name="Victron VE.Direct")
    out.reading.power_kw = summary.pv_w / 1000.0
    out.reading.e_daily_kwh = summary.today_kwh if summary.has_yield else -1
    out.reading.e_total_kwh = summary.total_kwh if summary.has_yield else -1
    out.reading.status = 1 if out.reading.power_kw > 0 else 0
    out.extra = summary.extra
    if errors:
        log.warning("VE.Direct: %s", "; ".join(errors))
    return out
