"""Podaci za dashboard (data.cpp): stanje uživo, krivulja dana, dnevni/mjesečni/godišnji iznosi, rekordi i ušteda."""
from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import Db, HourAggregate
from .util import add_days, first_of_month, iso_date, local_date, local_midnight, local_tm, months_back, now, utc_text

STALE_AFTER_S = 10 * 60
E_DAILY_FROM_HOUR = 1  # E-daily prije 01:00 može još nositi jučerašnji iznos
CURVE_BUCKET_S = 300
MAX_BAR_DAYS = 31
RECORDS_TTL_S = 15 * 60
MONTHS_HISTORY = 24


@dataclass
class DayKwh:
    date: dt.date
    kwh: float = 0.0
    load: float | None = None
    imported: float | None = None
    exported: float | None = None


def savings(s: dict[str, Any], produced_kwh: float, export_kwh: float | None) -> float:
    exported = min(max(export_kwh or 0.0, 0.0), max(produced_kwh, 0.0))
    return (produced_kwh - exported) * s["price_kwh"] + exported * s["feedin_price_kwh"]


def days_from_aggregates(hours: list[HourAggregate], start: dt.date, end: dt.date) -> list[DayKwh]:
    acc: dict[dt.date, dict[str, Any]] = {}
    for h in hours:
        a = acc.setdefault(local_date(h.hour), {"e_daily": None, "tmin": None, "tmax": None, "n_total": 0, "n_load": 0,
                                                "load": 0.0, "imp": 0.0, "exp": 0.0})
        if local_tm(h.hour).tm_hour >= E_DAILY_FROM_HOUR and h.e_daily_max is not None:
            a["e_daily"] = h.e_daily_max if a["e_daily"] is None else max(a["e_daily"], h.e_daily_max)
        if h.e_total_min is not None:
            a["tmin"] = h.e_total_min if a["tmin"] is None else min(a["tmin"], h.e_total_min)
        if h.e_total_max is not None:
            a["tmax"] = h.e_total_max if a["tmax"] is None else max(a["tmax"], h.e_total_max)
        a["n_total"] += h.n_total
        if h.n_load > 0:
            a["n_load"] += h.n_load
            a["load"] += h.load_avg or 0
            a["imp"] += h.import_avg or 0
            a["exp"] += h.export_avg or 0
    out = []
    d = start
    while d <= end:
        day = DayKwh(d)
        a = acc.get(d)
        if a:
            if a["e_daily"] is not None and a["e_daily"] > 0:
                day.kwh = a["e_daily"]
            elif a["n_total"] >= 2 and a["tmin"] is not None and a["tmax"] is not None:
                day.kwh = a["tmax"] - a["tmin"]
            if a["n_load"] > 0:
                day.load, day.imported, day.exported = a["load"], a["imp"], a["exp"]
        out.append(day)
        d = add_days(d, 1)
    return out


def _opt(v: float | None) -> float | None:
    return v


class DataService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._records: dict[str, Any] | None = None
        self._records_at = 0
        self._all_days: list[DayKwh] = []

    def _daily(self, db: Db, start: dt.date, end: dt.date) -> list[DayKwh]:
        return days_from_aggregates(db.hourly_aggregates(local_midnight(start), local_midnight(add_days(end, 1))), start, end)

    def daily(self, start: dt.date, end: dt.date) -> list[DayKwh]:
        with Db(self.db_path) as db:
            return self._daily(db, start, end)

    def peak_between(self, start: int, end: int) -> tuple[int, float] | None:
        with Db(self.db_path) as db:
            return db.peak_power_between(start, end)

    def _realtime(self, db: Db, s: dict[str, Any], month: list[DayKwh]) -> dict[str, Any]:
        t = now()
        last = db.latest()
        stale = not last or t - last.ts > STALE_AFTER_S
        power = last.power_kw if last else 0.0
        midnight = local_midnight(local_date(t))
        expected = (t - midnight) / max(s["poll_interval_s"], 1)
        count = db.count_between(midnight, t + 1)
        return {
            "power_kw": power, "running": not stale and power > 0, "stale": stale,
            "day_kwh": month[-1].kwh if month else 0.0, "month_kwh": sum(d.kwh for d in month),
            "total_kwh": last.e_total_kwh if last else 0.0, "status": last.status if last else 0,
            "pf": last.pf if last and last.pf is not None and not stale else None,
            "load_kw": last.load_kw if last and last.load_kw is not None and not stale else None,
            "availability": min(100.0, count / expected * 100) if expected >= 1 else None,
            "updated_at": last.ts if last else None,
            "extra": last.extra if last and not stale else {},
        }

    def _records_json(self, db: Db) -> dict[str, Any]:
        t = now()
        if self._records is not None and t - self._records_at < RECORDS_TTL_S:
            return self._records
        rec: dict[str, Any] = {}
        first = db.first_timestamp()
        if first:
            first_day, today = local_date(first), local_date(t)
            days = self._daily(db, first_day, today)
            months: dict[dt.date, float] = {}
            for d in days:
                months[first_of_month(d.date)] = months.get(first_of_month(d.date), 0.0) + d.kwh
            rec["first_day"] = iso_date(first_day)
            if days:
                best = max(days, key=lambda x: x.kwh)  # prvi najveći, kao std::max_element
                rec["best_day"] = [iso_date(best.date), best.kwh]
            if months:
                bm = max(months.items(), key=lambda kv: kv[1])
                rec["best_month"] = [iso_date(bm[0]), bm[1]]
            peak = db.peak_power()
            if peak:
                rec["peak_power"] = [peak[0], peak[1]]
            rec["producing_days"] = sum(1 for d in days if d.kwh > 0)
            self._all_days = days
        self._records, self._records_at = rec, t
        return rec

    def _savings_json(self, s: dict[str, Any], recent: list[DayKwh]) -> dict[str, Any]:
        if not recent or not self._records or "first_day" not in self._records:
            return {}
        today = recent[-1].date
        month_start, year_start = first_of_month(today), dt.date(today.year, 1, 1)
        day = month = year = 0.0
        total = sum(savings(s, d.kwh, d.exported) for d in self._all_days if d.date < recent[0].date)
        metered = False
        for d in recent:
            v = savings(s, d.kwh, d.exported)
            metered = metered or d.exported is not None
            total += v
            if d.date >= year_start:
                year += v
            if d.date >= month_start:
                month += v
            if d.date == today:
                day = v
        return {"today": day, "month": month, "year": year, "total": total, "first_day": self._records["first_day"],
                "metered": metered}

    def dashboard(self, s: dict[str, Any]) -> dict[str, Any]:
        with self._lock, Db(self.db_path) as db:
            t = now()
            today = local_date(t)
            month_start = first_of_month(today)
            prev_month_start = months_back(month_start, 1)
            year_start = dt.date(today.year, 1, 1)
            history_start = min(months_back(month_start, MONTHS_HISTORY - 1), dt.date(today.year - 1, 1, 1))
            days = self._daily(db, history_start, today)
            try:
                last_year_end = dt.date(today.year - 1, today.month, today.day)
            except ValueError:  # 29. veljače → 28. veljače
                last_year_end = dt.date(today.year - 1, 2, 28)
            last_year_start = dt.date(last_year_end.year, 1, 1)
            bars_start = min(prev_month_start, add_days(today, -(MAX_BAR_DAYS - 1)))
            month: list[DayKwh] = []
            daily_json = []
            months: dict[dt.date, float] = {}
            year_this = year_last = 0.0
            for d in days:
                if d.date >= month_start:
                    month.append(d)
                if d.date >= bars_start:
                    daily_json.append([iso_date(d.date), d.kwh, d.load, d.imported, d.exported])
                months[first_of_month(d.date)] = months.get(first_of_month(d.date), 0.0) + d.kwh
                if d.date >= year_start:
                    year_this += d.kwh
                if last_year_start <= d.date <= last_year_end:
                    year_last += d.kwh
            monthly = []
            for i in range(MONTHS_HISTORY - 1, -1, -1):
                m = months_back(month_start, i)
                monthly.append([iso_date(m), months.get(m, 0.0)])
            curve = [[b[0], b[1], b[2]] for b in db.power_buckets(local_midnight(today), local_midnight(add_days(today, 1)), CURVE_BUCKET_S)]
            realtime = self._realtime(db, s, month)
            records = self._records_json(db)
            return {"now": t, "today": iso_date(today), "realtime": realtime, "curve": curve, "daily": daily_json,
                    "monthly": monthly, "year": [year_this, year_last], "records": records, "savings": self._savings_json(s, days)}

    def invalidate(self) -> None:
        """Nakon uvoza povijesti rekordi se računaju iznova."""
        with self._lock:
            self._records = None

    def db_info(self) -> dict[str, Any]:
        with self._lock:
            if not self.db_path.exists():
                return {"path": str(self.db_path), "readings": 0}
            with Db(self.db_path) as db:
                first, last = db.first_timestamp(), db.latest()
                return {"path": str(self.db_path), "readings": db.total_readings(),
                        "first": utc_text(first) if first else None, "last": utc_text(last.ts) if last else None}
