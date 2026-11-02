"""Vrijeme, datoteke i zapisnik – isto kao util.cpp (lokalno vrijeme prema TZ-u kontejnera / Home Assistanta)."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("solari")

UTC_FORMAT = "%Y-%m-%d %H:%M:%S"


def now() -> int:
    return int(time.time())


def utc_text(ts: float) -> str:
    """Isti format kao Python i C++ verzija: 'YYYY-MM-DD HH:MM:SS' u UTC-u (stupac ts_utc)."""
    return time.strftime(UTC_FORMAT, time.gmtime(ts))


def parse_utc_text(text: str) -> int | None:
    try:
        return int(dt.datetime.strptime(text, UTC_FORMAT).replace(tzinfo=dt.timezone.utc).timestamp())
    except (ValueError, TypeError):
        return None


def local_date(ts: float) -> dt.date:
    return dt.datetime.fromtimestamp(ts).date()


def local_midnight(day: dt.date) -> int:
    return int(time.mktime((day.year, day.month, day.day, 0, 0, 0, 0, 0, -1)))


def local_tm(ts: float) -> time.struct_time:
    return time.localtime(ts)


def iso_date(day: dt.date) -> str:
    return day.isoformat()


def add_days(day: dt.date, n: int) -> dt.date:
    return day + dt.timedelta(days=n)


def first_of_month(day: dt.date) -> dt.date:
    return day.replace(day=1)


def months_back(first: dt.date, n: int) -> dt.date:
    index = first.year * 12 + (first.month - 1) - n
    return dt.date(index // 12, index % 12 + 1, 1)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_atomic(path: Path, data: bytes | str, private: bool = False) -> None:
    """Upis preko privremene datoteke i preimenovanja (kao write_file_atomic)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        if private:
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path: Path, value: Any, private: bool = False) -> None:
    write_atomic(path, json.dumps(value, ensure_ascii=False, indent=2), private)
