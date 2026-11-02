"""Mjesečni izvještaj (report.cpp) – isti JSON kao Windows verzija (iscrtava ga web/settings.js) i CSV za Excel."""
from __future__ import annotations

import calendar
import datetime as dt
import time
from typing import Any

from . import i18n
from .data import DataService, DayKwh, savings
from .i18n import tr
from .util import add_days, iso_date, local_date, local_midnight, now


def _month_kwh(data: DataService, year: int, month: int) -> float:
    if year < 1:
        return 0.0
    first = dt.date(year, month, 1)
    return sum(d.kwh for d in data.daily(first, dt.date(year, month, calendar.monthrange(year, month)[1])))


def build_report(data: DataService, s: dict[str, Any], year: int, month: int) -> dict[str, Any]:
    today = local_date(now())
    try:
        first = dt.date(year, month, 1)
    except ValueError as e:
        raise RuntimeError(tr("Izvještaj za budući mjesec nije moguć.")) from e
    if first > today:
        raise RuntimeError(tr("Izvještaj za budući mjesec nije moguć."))
    month_end = dt.date(year, month, calendar.monthrange(year, month)[1])
    until = min(month_end, today)
    days = data.daily(first, until)
    rows = []
    kwh = load = imported = exported = total_savings = 0.0
    metered = False
    best: DayKwh | None = None
    for d in days:
        sv = savings(s, d.kwh, d.exported)
        rows.append({"date": iso_date(d.date), "kwh": d.kwh, "load": d.load, "import": d.imported, "export": d.exported,
                     "self": d.kwh - (d.exported or 0), "savings": sv})
        kwh += d.kwh
        total_savings += sv
        if d.load is not None:
            metered = True
            load += d.load
            imported += d.imported or 0
            exported += d.exported or 0
        if d.kwh > 0 and (best is None or d.kwh > best.kwh):
            best = d
    self_kwh = kwh - (exported if metered else 0)
    prev = add_days(first, -1)
    peak = data.peak_between(local_midnight(first), local_midnight(add_days(until, 1)))
    return {
        "plant": s["plant_name"], "location": s["location"], "kwp": s["peak_power_kwp"], "currency": s["currency"],
        "price": s["price_kwh"], "feedin": s["feedin_price_kwh"], "co2_factor": s["co2_factor"],
        "year": year, "month": month, "complete": until == month_end, "until": iso_date(until),
        "generated": time.strftime("%Y-%m-%dT%H:%M"), "metered": metered, "days": rows,
        "totals": {"kwh": kwh, "load": load if metered else None, "import": imported if metered else None,
                   "export": exported if metered else None, "self": self_kwh,
                   "self_share": self_kwh / kwh * 100 if metered and kwh > 0 else None,
                   "autarky": self_kwh / load * 100 if metered and load > 0 else None,
                   "savings": total_savings, "co2_kg": kwh * s["co2_factor"]},
        "compare": {"prev_month": _month_kwh(data, prev.year, prev.month), "last_year": _month_kwh(data, year - 1, month)},
        "best_day": {"date": iso_date(best.date), "kwh": best.kwh} if best else None,
        # uvezena povijest može imati samo dnevne iznose (snaga 0) – tada vrh nije poznat
        "peak": {"ts": time.strftime("%Y-%m-%dT%H:%M", time.localtime(peak[0])), "kw": peak[1]} if peak and peak[1] > 0 else None,
    }


def _format_date(pattern: str, d: dt.date) -> str:
    return (pattern.replace("{d:02}", f"{d.day:02}").replace("{m:02}", f"{d.month:02}").replace("{d}", str(d.day))
            .replace("{m}", str(d.month)).replace("{y}", str(d.year)))


def report_csv(r: dict[str, Any]) -> bytes:
    """UTF-8 s BOM-om; ';' i decimalni zarez kad ga jezik koristi."""
    meta = i18n.bundle(i18n.language()).get("meta", {})
    decimal, pattern = meta.get("decimal", ","), meta.get("date", "{d:02}.{m:02}.{y}.")
    sep = ";" if decimal == "," else ","
    cur = r.get("currency", "€")

    def num(v: Any) -> str:
        return f"{v:.2f}".replace(".", decimal) if isinstance(v, (int, float)) and not isinstance(v, bool) else ""

    lines = [sep.join([tr("Datum"), tr("Proizvodnja") + " (kWh)", tr("Potrošnja") + " (kWh)", tr("Iz mreže") + " (kWh)",
                       tr("Predaja u mrežu") + " (kWh)", tr("Vlastita potrošnja") + " (kWh)", tr("Ušteda") + f" ({cur})"])]
    for d in r["days"]:
        lines.append(sep.join([_format_date(pattern, dt.date.fromisoformat(d["date"])), num(d["kwh"]), num(d["load"]),
                               num(d["import"]), num(d["export"]), num(d["self"]), num(d["savings"])]))
    t = r["totals"]
    lines.append(sep.join([tr("Ukupno"), num(t["kwh"]), num(t["load"]), num(t["import"]), num(t["export"]), num(t["self"]),
                           num(t["savings"])]))
    return ("﻿" + "\r\n".join(lines) + "\r\n").encode("utf-8")
