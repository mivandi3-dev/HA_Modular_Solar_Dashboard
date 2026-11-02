"""Prijevodi poruka dashboarda – isti rječnici kao sučelje (web/i18n)."""
from __future__ import annotations

import contextvars
import json
from pathlib import Path
from typing import Any

LANGUAGES = ("hr", "en", "de", "fr", "it", "tr", "zh", "ja", "ko", "es")
_dir = Path(__file__).resolve().parent.parent / "web" / "i18n"
_cache: dict[str, dict[str, Any]] = {}
_lang: contextvars.ContextVar[str] = contextvars.ContextVar("lang", default="hr")


def set_dir(path: Path) -> None:
    global _dir
    _dir = path
    _cache.clear()


def _load(code: str) -> dict[str, Any]:
    if code not in _cache:
        try:
            _cache[code] = json.loads((_dir / f"{code}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache[code] = {"meta": {}, "strings": {}}
        _cache[code].setdefault("strings", {})
    return _cache[code]


def set_language(code: str) -> None:
    _lang.set(code if code in LANGUAGES else "hr")


def tr(key: str, args: dict[str, Any] | None = None) -> str:
    text = _load(_lang.get())["strings"].get(key) or key
    for k, v in (args or {}).items():
        text = text.replace("{" + k + "}", str(v))
    return text


def bundle(code: str) -> dict[str, Any]:
    lang = code if code in LANGUAGES else "hr"
    data = _load(lang)
    return {"lang": lang, "meta": data.get("meta", {}), "strings": data["strings"],
            "languages": {c: _load(c).get("meta", {}).get("name", c) for c in LANGUAGES}}
