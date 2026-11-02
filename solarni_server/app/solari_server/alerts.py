"""Obavijesti e-poštom o stanju elektrane (alerts.cpp): uređaj ne odgovara, inverter javlja grešku, niska proizvodnja
prema prognozi zračenja. Najviše 20 poruka dnevno; stanje se pamti u alerts.json."""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .i18n import fmt_num, tr
from .util import iso_date, local_date, local_tm, log, read_json, write_json

MAX_PER_DAY = 20
LOW_FROM_HOUR, LOW_TO_HOUR = 14, 17
LOW_RATIO = 0.5
LOW_MIN_EXPECTED_KWP_H = 0.5
PERFORMANCE_RATIO = 0.8
INVERTER_FAULTS = {0x0300: "Shutdown: Fault", 0x0302: "Shutdown: OVGR", 0x0305: "Shutdown: manual startup required",
                   0x0306: "Shutdown: DC switches disconnected", 0x0307: "Shutdown: rapid cutoff"}


@dataclass
class AlertState:
    offline_sent: bool = False
    fault_sent: bool = False
    low_day: str = ""
    sent_day: str = ""
    sent_count: int = 0


@dataclass
class Observation:
    now: int
    ok: bool
    last_ok: int | None = None
    status: int | None = None
    error: str = ""
    day_kwh: float | None = None
    expected_kwh: float | None = None


@dataclass
class MailMessage:
    subject: str
    body: str


def _time_text(t: float, fmt: str) -> str:
    return time.strftime(fmt, time.localtime(t))


def subject(s: dict[str, Any], text: str) -> str:
    return f"[{tr('Solarni monitor')}] {s['plant_name']}: {text}"


def footer(s: dict[str, Any], t: float) -> str:
    return "\n\n— " + tr("Solarni monitor · {plant} · {time}", {"plant": s["plant_name"], "time": _time_text(t, "%d.%m.%Y. %H:%M")})


def wants_forecast(s: dict[str, Any], state: AlertState, t: float) -> bool:
    h = local_tm(t).tm_hour
    return s["alert_low_production"] and LOW_FROM_HOUR <= h < LOW_TO_HOUR and state.low_day != iso_date(local_date(t))


def _parse_local(text: str) -> float | None:
    try:
        return time.mktime(dt.datetime.strptime(text[:16], "%Y-%m-%dT%H:%M").timetuple())
    except (ValueError, TypeError):
        return None


def expected_until(hourly: list[Any], t: float, kwp: float) -> float:
    """Očekivana energija (kWh) od ponoći do t iz satnog zračenja (W/m² u satu koji ZAVRŠAVA u navedeno vrijeme)."""
    total = 0.0
    today = local_date(t)
    for h in hourly:
        if not isinstance(h, list) or len(h) < 2 or not isinstance(h[0], str) or not isinstance(h[1], (int, float)):
            continue
        end = _parse_local(h[0])
        if end is None:
            continue
        start = end - 3600
        if local_date(start + 1800) != today:
            continue
        kw = max(h[1], 0.0) / 1000 * kwp * PERFORMANCE_RATIO
        total += kw * min(max((min(t, end) - start) / 3600, 0.0), 1.0)
    return total


def evaluate_alerts(s: dict[str, Any], state: AlertState, obs: Observation) -> tuple[AlertState, list[MailMessage]]:
    state = AlertState(**asdict(state))
    device = tr("Inverter") if s["device_type"] == "inverter" else tr("Logger")
    msgs: list[MailMessage] = []
    day = iso_date(local_date(obs.now))
    hour = local_tm(obs.now).tm_hour
    if s["alert_offline_min"] > 0:
        if obs.ok and state.offline_sent:
            msgs.append(MailMessage(subject(s, tr("{device} ponovno radi", {"device": device})),
                                    tr("{device} {host} ponovno odgovara i podaci se bilježe.", {"device": device, "host": s["modbus_host"]})))
            state.offline_sent = False
        elif not obs.ok and not state.offline_sent and obs.last_ok:
            minutes = (obs.now - obs.last_ok) // 60
            if minutes >= s["alert_offline_min"]:
                text = tr("{device} {host} ne odgovara {n} min (zadnje očitanje {time}).",
                          {"device": device, "host": s["modbus_host"], "n": minutes, "time": _time_text(obs.last_ok, "%d.%m. %H:%M")})
                if obs.error:
                    text += "\n\n" + tr("Zadnja greška: {error}", {"error": obs.error})
                msgs.append(MailMessage(subject(s, tr("{device} nedostupan", {"device": device})), text))
                state.offline_sent = True
    if s["alert_fault"] and s["device_type"] == "inverter" and obs.ok and obs.status is not None:
        fault = INVERTER_FAULTS.get(obs.status)
        if fault and not state.fault_sent:
            msgs.append(MailMessage(subject(s, tr("inverter javlja grešku")),
                                    tr("Inverter javlja stanje „{status}“ (0x{code:04X}) i ne proizvodi. Provjerite inverter "
                                       "u aplikaciji FusionSolar.", {"status": fault, "code:04X": f"{obs.status:04X}"})))
            state.fault_sent = True
        elif not fault and state.fault_sent:
            msgs.append(MailMessage(subject(s, tr("inverter ponovno radi")), tr("Inverter više ne javlja grešku.")))
            state.fault_sent = False
    if (s["alert_low_production"] and obs.ok and obs.day_kwh is not None and obs.expected_kwh is not None
            and LOW_FROM_HOUR <= hour < LOW_TO_HOUR and state.low_day != day
            and obs.expected_kwh >= LOW_MIN_EXPECTED_KWP_H * s["peak_power_kwp"]):
        if obs.day_kwh < LOW_RATIO * obs.expected_kwh:
            msgs.append(MailMessage(subject(s, tr("niska proizvodnja")), tr(
                "Danas je do {time} proizvedeno {kwh} kWh, a prema prognozi zračenja očekivano je oko "
                "{expected} kWh ({pct} %). Mogući uzroci: prljavi paneli, ispao string, isključen inverter ili sjena.",
                {"time": _time_text(obs.now, "%H:%M"), "kwh": fmt_num(obs.day_kwh, 0), "expected": fmt_num(obs.expected_kwh, 0),
                 "pct": fmt_num(obs.day_kwh / obs.expected_kwh * 100, 0)})))
        state.low_day = day  # provjera jednom dnevno (i kad je sve u redu)
    if msgs:
        count = state.sent_count if state.sent_day == day else 0
        allowed = max(0, MAX_PER_DAY - count)
        if len(msgs) > allowed:
            log.warning("Dnevno ograničenje obavijesti – %d poruka nije poslano", len(msgs) - allowed)
            msgs = msgs[:allowed]
        for m in msgs:
            m.body += footer(s, obs.now)
        state.sent_day, state.sent_count = day, count + len(msgs)
    return state, msgs


def test_message(s: dict[str, Any], t: float) -> MailMessage:
    return MailMessage(subject(s, tr("probna poruka")), tr("Ovo je probna poruka. Obavijesti o elektrani stižu na ovu adresu.") + footer(s, t))


def load_state(path: Path) -> AlertState:
    j = read_json(path, {}) or {}
    try:
        return AlertState(bool(j.get("offline_sent")), bool(j.get("fault_sent")), str(j.get("low_day", "")),
                          str(j.get("sent_day", "")), int(j.get("sent_count", 0)))
    except (TypeError, ValueError):
        return AlertState()


def save_state(path: Path, state: AlertState) -> None:
    write_json(path, asdict(state))
