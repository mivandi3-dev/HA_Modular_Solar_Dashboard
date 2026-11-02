"""SQLite povijest očitanja (storage.cpp) – ista shema i format vremena kao Windows i Python verzija, pa se baze mogu
međusobno uvoziti (i kopirati s Windows poslužitelja: C:\\ProgramData\\SolarniServer\\data\\solar.db)."""
from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .i18n import tr
from .util import add_days, iso_date, local_midnight, parse_utc_text, utc_text

SCHEMA = ("CREATE TABLE IF NOT EXISTS readings (ts_utc TEXT PRIMARY KEY, power_kw REAL, e_daily_kwh REAL,"
          " e_total_kwh REAL, pf REAL, status INTEGER, load_kw REAL)")


@dataclass
class Reading:
    power_kw: float = 0.0
    e_daily_kwh: float = 0.0
    e_total_kwh: float = 0.0
    pf: float | None = 0.0
    status: int = 0


@dataclass
class LatestReading:
    ts: int = 0
    power_kw: float = 0.0
    e_daily_kwh: float = 0.0
    e_total_kwh: float = 0.0
    pf: float | None = None
    load_kw: float | None = None
    status: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class HourAggregate:
    hour: int
    n_total: int
    e_daily_max: float | None
    e_total_min: float | None
    e_total_max: float | None
    power_max: float | None
    n_load: int
    load_avg: float | None
    export_avg: float | None
    import_avg: float | None


class Db:
    def __init__(self, path: Path, read_only: bool = False) -> None:
        self.path = path
        if read_only:
            self.conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), timeout=10)
        self.conn.execute("PRAGMA journal_mode=WAL")
        # kao Windows verzija (SQLITE_DEFAULT_WAL_SYNCHRONOUS=1): u WAL-u sinkronizacija samo pri checkpointu –
        # manje upisa na SD karticu (Raspberry Pi), baza ostaje dosljedna i nakon nestanka struje
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute(SCHEMA)
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(readings)")]
        if "extra" not in cols:  # stupac extra (JSON s podacima uređaja) – starije baze ga nemaju
            self.conn.execute("ALTER TABLE readings ADD COLUMN extra TEXT")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Db":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------ upis
    def insert(self, ts: int, r: Reading, load_kw: float | None, extra: dict[str, Any] | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO readings (ts_utc, power_kw, e_daily_kwh, e_total_kwh, pf, status, load_kw, extra)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (utc_text(ts), r.power_kw, r.e_daily_kwh, r.e_total_kwh, r.pf, int(r.status), load_kw,
             json.dumps(extra) if extra else ""))
        self.conn.commit()

    def insert_day_yield(self, ts: int, kwh: float) -> None:
        self.conn.execute("INSERT OR IGNORE INTO readings (ts_utc, power_kw, e_daily_kwh) VALUES (?, 0, ?)", (utc_text(ts), kwh))
        self.conn.commit()

    # ------------------------------------------------------------ čitanje
    def day_start_total(self, day_start: int) -> float | None:
        row = self.conn.execute(
            "SELECT e_total_kwh FROM readings WHERE ts_utc < ? AND ts_utc >= ? AND e_total_kwh > 0 ORDER BY ts_utc DESC LIMIT 1",
            (utc_text(day_start), utc_text(day_start - 7 * 86400))).fetchone()
        if row:
            return row[0]
        row = self.conn.execute("SELECT e_total_kwh FROM readings WHERE ts_utc >= ? AND e_total_kwh > 0 ORDER BY ts_utc LIMIT 1",
                                (utc_text(day_start),)).fetchone()
        return row[0] if row else None

    def latest(self) -> LatestReading | None:
        # uvezena povijest (samo E-daily, bez ukupne energije) nije stvarno očitanje uređaja
        row = self.conn.execute(
            "SELECT ts_utc, power_kw, e_daily_kwh, e_total_kwh, pf, status, load_kw, extra FROM readings"
            " WHERE e_total_kwh IS NOT NULL ORDER BY ts_utc DESC LIMIT 1").fetchone()
        if not row:
            return None
        extra: dict[str, Any] = {}
        if row[7]:
            try:
                parsed = json.loads(row[7])
                extra = parsed if isinstance(parsed, dict) else {}
            except ValueError:
                extra = {}
        return LatestReading(parse_utc_text(row[0]) or 0, row[1] or 0.0, row[2] or 0.0, row[3] or 0.0, row[4], row[6],
                             int(row[5] or 0), extra)

    def hourly_aggregates(self, start: int, end: int) -> list[HourAggregate]:
        rows = self.conn.execute(
            "SELECT substr(ts_utc, 1, 13), COUNT(e_total_kwh), MAX(e_daily_kwh), MIN(e_total_kwh), MAX(e_total_kwh),"
            " MAX(power_kw), COUNT(load_kw), AVG(load_kw), AVG(MAX(COALESCE(power_kw, 0) - load_kw, 0)),"
            " AVG(MAX(load_kw - COALESCE(power_kw, 0), 0)) FROM readings WHERE ts_utc >= ? AND ts_utc < ? GROUP BY 1 ORDER BY 1",
            (utc_text(start), utc_text(end))).fetchall()
        return [HourAggregate(parse_utc_text(r[0] + ":00:00") or 0, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9])
                for r in rows]

    def power_buckets(self, start: int, end: int, seconds: int) -> list[tuple[int, float, float | None]]:
        return [(int(r[0]), r[1], r[2]) for r in self.conn.execute(
            "SELECT (CAST(strftime('%s', ts_utc) AS INTEGER) / ?) * ?, AVG(power_kw), AVG(load_kw) FROM readings"
            " WHERE ts_utc >= ? AND ts_utc < ? AND power_kw IS NOT NULL GROUP BY 1 ORDER BY 1",
            (seconds, seconds, utc_text(start), utc_text(end)))]

    def count_between(self, start: int, end: int) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM readings WHERE ts_utc >= ? AND ts_utc < ?",
                                 (utc_text(start), utc_text(end))).fetchone()[0]

    def peak_power(self) -> tuple[int, float] | None:
        row = self.conn.execute("SELECT ts_utc, power_kw FROM readings WHERE power_kw IS NOT NULL ORDER BY power_kw DESC LIMIT 1").fetchone()
        return (parse_utc_text(row[0]) or 0, row[1]) if row else None

    def peak_power_between(self, start: int, end: int) -> tuple[int, float] | None:
        row = self.conn.execute(
            "SELECT ts_utc, power_kw FROM readings WHERE ts_utc >= ? AND ts_utc < ? AND power_kw IS NOT NULL"
            " ORDER BY power_kw DESC LIMIT 1", (utc_text(start), utc_text(end))).fetchone()
        return (parse_utc_text(row[0]) or 0, row[1]) if row else None

    def first_timestamp(self) -> int | None:
        row = self.conn.execute("SELECT MIN(ts_utc) FROM readings").fetchone()
        return parse_utc_text(row[0]) if row and row[0] else None

    def total_readings(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

    # ------------------------------------------------------------ uvoz i kopije
    def import_history(self, source: Path) -> int:
        if source.resolve() == self.path.resolve():
            raise RuntimeError(tr("Odabrana je ista baza koju aplikacija već koristi."))
        before = self.total_readings()
        try:
            src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
            try:
                ok = src.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='readings'").fetchone()[0]
            finally:
                src.close()
        except sqlite3.DatabaseError as e:
            raise RuntimeError(tr("Odabrana datoteka nije baza Solarnog monitora (nema tablice readings).")) from e
        if not ok:
            raise RuntimeError(tr("Odabrana datoteka nije baza Solarnog monitora (nema tablice readings)."))
        self.conn.execute("ATTACH DATABASE ? AS src", (str(source),))
        try:
            cols = [r[1] for r in self.conn.execute("PRAGMA src.table_info(readings)")]
            has_load = "load_kw" in cols
            rows = self.conn.execute(
                "SELECT ts_utc, power_kw, e_daily_kwh, e_total_kwh, pf, status, " + ("load_kw" if has_load else "NULL")
                + " FROM src.readings").fetchall()
            valid = [r for r in rows if valid_history_row(r)]  # i datoteka iz preglednika je neprovjereni ulaz
            self.conn.executemany("INSERT OR IGNORE INTO readings (ts_utc, power_kw, e_daily_kwh, e_total_kwh, pf, status, load_kw)"
                                  " VALUES (?, ?, ?, ?, ?, ?, ?)", valid)
            self.conn.commit()
        finally:
            self.conn.execute("DETACH DATABASE src")
        return self.total_readings() - before

    def backup_to(self, target: Path) -> None:
        dst = sqlite3.connect(str(target))
        try:
            self.conn.backup(dst)
        finally:
            dst.close()


def valid_history_row(r: tuple[Any, ...]) -> bool:
    ts, power, daily, total, pf, status, load = r
    if not isinstance(ts, str) or len(ts) != 19 or parse_utc_text(ts) is None:
        return False

    def ok(v: Any, lo: float, hi: float) -> bool:
        return v is None or (isinstance(v, (int, float)) and math.isfinite(v) and lo <= v <= hi)

    return (ok(power, -1e6, 1e6) and ok(daily, -1e6, 1e7) and ok(total, -1e6, 1e12) and ok(pf, -2, 2) and ok(load, -1e6, 1e6)
            and (status is None or (isinstance(status, (int, float)) and 0 <= status <= 0xFFFFFFFF)))


COMPACT_BUCKET_S = 300
COMPACT_STATE = "PRAGMA user_version"  # dokle je povijest već sažeta (dan, YYYYMMDD) – ne obrađuje se iznova


def compact_history(db: Db, keep_days: int, today: dt.date, max_days: int = 60) -> int:
    """Očitanja starija od keep_days dana sažima na 5-minutne prosjeke (snaga, mjerač, cos φ – prosjek; energija – najveća
    vrijednost; podaci uređaja – zadnji). Najveća snaga svakog dana ostaje kao zasebno očitanje (rekordi, izvještaji).
    Dnevni iznosi, grafovi i ušteda ostaju isti; baza je ~30 × manja za stare dane (10 s → 5 min).
    Obrađuje najviše max_days dana po pozivu (poller ga zove jednom dnevno), pa prvi prolaz ne blokira bilježenje.
    Vraća broj uklonjenih redaka."""
    if keep_days <= 0:
        return 0
    cutoff = add_days(today, -keep_days)
    done = db.conn.execute(COMPACT_STATE).fetchone()[0]
    first = db.first_timestamp()
    if first is None:
        return 0
    start = dt.datetime.fromtimestamp(first).date()
    if done:
        start = max(start, add_days(dt.date(done // 10000, done // 100 % 100, done % 100), 1))
    removed = 0
    day = start
    for _ in range(max_days):
        if day >= cutoff:
            break
        lo, hi = utc_text(local_midnight(day)), utc_text(local_midnight(add_days(day, 1)))
        n = db.conn.execute("SELECT COUNT(*) FROM readings WHERE ts_utc >= ? AND ts_utc < ?", (lo, hi)).fetchone()[0]
        if n > 24 * 3600 // COMPACT_BUCKET_S + 1:
            with db.conn:
                peak = db.conn.execute("SELECT ts_utc FROM readings WHERE ts_utc >= ? AND ts_utc < ? AND power_kw IS NOT NULL"
                                       " ORDER BY power_kw DESC LIMIT 1", (lo, hi)).fetchone()
                keep = peak[0] if peak else ""
                db.conn.execute("CREATE TEMP TABLE IF NOT EXISTS compact (ts_utc TEXT PRIMARY KEY, power_kw REAL, e_daily_kwh REAL,"
                                " e_total_kwh REAL, pf REAL, status INTEGER, load_kw REAL, extra TEXT)")
                db.conn.execute("DELETE FROM compact")
                db.conn.execute(
                    "INSERT INTO compact SELECT datetime((CAST(strftime('%s', ts_utc) AS INTEGER) / ?) * ?, 'unixepoch'),"
                    " AVG(power_kw), MAX(e_daily_kwh), MAX(e_total_kwh), AVG(pf), MAX(status), AVG(load_kw),"
                    " (SELECT r2.extra FROM readings r2 WHERE r2.ts_utc >= ? AND r2.ts_utc < ? AND"
                    "  CAST(strftime('%s', r2.ts_utc) AS INTEGER) / ? = CAST(strftime('%s', r.ts_utc) AS INTEGER) / ?"
                    "  ORDER BY r2.ts_utc DESC LIMIT 1)"
                    " FROM readings r WHERE ts_utc >= ? AND ts_utc < ? AND ts_utc != ? GROUP BY 1",
                    (COMPACT_BUCKET_S, COMPACT_BUCKET_S, lo, hi, COMPACT_BUCKET_S, COMPACT_BUCKET_S, lo, hi, keep))
                db.conn.execute("DELETE FROM readings WHERE ts_utc >= ? AND ts_utc < ? AND ts_utc != ?", (lo, hi, keep))
                db.conn.execute("INSERT OR IGNORE INTO readings SELECT * FROM compact")
                after = db.conn.execute("SELECT COUNT(*) FROM readings WHERE ts_utc >= ? AND ts_utc < ?", (lo, hi)).fetchone()[0]
                removed += n - after
        db.conn.execute(f"PRAGMA user_version = {day.year * 10000 + day.month * 100 + day.day}")
        day = add_days(day, 1)
    db.conn.commit()
    return removed


def daily_backup(db_path: Path, backup_dir: Path, keep_days: int, today: dt.date) -> Path | None:
    """Kopija za danas (ako je nema) i brisanje kopija starijih od keep_days."""
    if keep_days <= 0 or not db_path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"solar_{iso_date(today)}.db"
    created = None
    if not target.exists():
        tmp = target.with_suffix(".db.tmp")
        with Db(db_path) as db:
            db.backup_to(tmp)
        tmp.replace(target)
        created = target
    cutoff = add_days(today, -keep_days)
    for f in backup_dir.glob("solar_????-??-??.db"):
        try:
            if dt.date.fromisoformat(f.name[6:16]) < cutoff:
                f.unlink()
        except ValueError:
            continue
    return created


def local_day_bounds(day: dt.date) -> tuple[int, int]:
    return local_midnight(day), local_midnight(add_days(day, 1))
