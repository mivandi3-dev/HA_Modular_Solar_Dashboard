"""Uvoz povijesti dnevne proizvodnje iz izvoza logova SmartLoggera (smartlogger_export.cpp).

perfmg_day.emap (little-endian): zaglavlje 8 B, zapisi po 16 B: u16 uređaj (0x0002 = elektrana), u16 KPI (0x3011 = dnevna
proizvodnja), u32 razdoblje, u32 vrijeme (Unix, 00:00 UTC dana), i32 vrijednost (0,01 kWh; -1 = nema podatka).
Arhiva se otvara u memoriji (zipfile) – i ZIP-ovi unutar ZIP-a (jedna razina), bez raspakiravanja na disk."""
from __future__ import annotations

import datetime as dt
import io
import struct
import zipfile
from dataclasses import dataclass

from .i18n import tr
from .storage import Db
from .util import add_days, local_midnight

FILE = "perfmg_day.emap"
HEADER, RECORD = 8, 16
PLANT_DEVICE, KPI_DAY_YIELD = 0x0002, 0x3011
FIRST_VALID_TS = 946_684_800  # 1. 1. 2000.
IMPORT_HOUR = 23
MAX_UNPACKED = 512 * 1024 * 1024


def parse_perfmg_day(data: bytes) -> dict[dt.date, float]:
    if len(data) < HEADER + RECORD:
        raise RuntimeError(tr("Datoteka nije izvoz SmartLoggera."))
    days: dict[dt.date, float] = {}
    for at in range(HEADER, len(data) - RECORD + 1, RECORD):
        device, kpi, _period, ts, value = struct.unpack_from("<HHIIi", data, at)
        if device != PLANT_DEVICE or kpi != KPI_DAY_YIELD or value < 0 or ts < FIRST_VALID_TS:
            continue
        days[dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()] = value / 100
    return days


def _not_found() -> str:
    return tr("U izvozu nema datoteke {file} – izvezite logove SmartLoggera (ne invertera).", {"file": FILE})


def _from_zip(z: zipfile.ZipFile, depth: int) -> bytes | None:
    for info in z.infolist():
        if info.filename.rsplit("/", 1)[-1] == FILE and info.file_size <= MAX_UNPACKED:
            return z.read(info)
    if depth == 0:
        return None
    for info in z.infolist():
        if info.filename.lower().endswith(".zip") and info.file_size <= MAX_UNPACKED:
            try:
                found = _from_zip(zipfile.ZipFile(io.BytesIO(z.read(info))), depth - 1)
            except zipfile.BadZipFile:
                continue
            if found:
                return found
    return None


def read_perfmg_day(name: str, data: bytes) -> bytes:
    """Sadržaj perfmg_day.emap iz log.zip (i ZIP-ova u njemu) ili sama .emap datoteka."""
    if name.lower().endswith(".zip") or data[:2] == b"PK":
        try:
            found = _from_zip(zipfile.ZipFile(io.BytesIO(data)), 1)
        except zipfile.BadZipFile as e:
            raise RuntimeError(tr("Arhivu nije moguće raspakirati: {error}", {"error": e})) from e
        if not found:
            raise RuntimeError(_not_found())
        return found
    return data


@dataclass
class ExportImport:
    imported: int = 0
    skipped: int = 0
    first: dt.date | None = None
    last: dt.date | None = None
    kwh: float = 0.0


def import_perfmg_days(db: Db, days: dict[dt.date, float], today: dt.date) -> ExportImport:
    """Po jedno očitanje (lokalno 23:00, E-daily = proizvodnja dana) za svaki dan prije danas koji još nema očitanja."""
    out = ExportImport()
    for day in sorted(days):
        if day >= today:
            continue
        start, end = local_midnight(day), local_midnight(add_days(day, 1))
        if db.count_between(start, end) > 0:
            out.skipped += 1
            continue
        db.insert_day_yield(end - (24 - IMPORT_HOUR) * 3600, days[day])
        out.imported += 1
        out.kwh += days[day]
        out.first = out.first or day
        out.last = day
    return out
