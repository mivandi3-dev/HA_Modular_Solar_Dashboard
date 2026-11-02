"""Prijevodi (i18n.cpp): ključ je hrvatski tekst, rječnici su web/i18n/<jezik>.json (isti kao sučelje).

Jezik poruke bira se po zahtjevu (zaglavlje X-Solari-Language) – zato je trenutni jezik ContextVar, a ne globalna varijabla.
"""
from __future__ import annotations

import contextvars
import json
import os
import threading
from pathlib import Path
from typing import Any

LANGUAGES = ("hr", "en", "de", "fr", "it", "tr", "zh", "ja", "ko", "es")

_lang: contextvars.ContextVar[str | None] = contextvars.ContextVar("solari_lang", default=None)
_default_lang = "hr"
_cache: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def i18n_dir() -> Path:
    env = os.environ.get("SOLARI_I18N_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "web" / "i18n"


def _load(code: str) -> dict[str, Any]:
    with _lock:
        if code in _cache:
            return _cache[code]
        data: dict[str, Any] = {"meta": {}, "strings": {}}
        try:
            data = json.loads((i18n_dir() / f"{code}.json").read_text(encoding="utf-8"))
            data.setdefault("strings", {})
            data.setdefault("meta", {})
        except (OSError, ValueError):
            pass
        _cache[code] = data
        return data


def is_language(code: str) -> bool:
    return code in LANGUAGES


def set_default_language(code: str) -> None:
    """Jezik pollera (obavijesti e-poštom) – postavke poslužitelja."""
    global _default_lang
    _default_lang = code if is_language(code) else "hr"


def set_language(code: str | None) -> None:
    _lang.set(code if code and is_language(code) else _default_lang)


def language() -> str:
    return _lang.get() or _default_lang


def tr(key: str, args: dict[str, Any] | None = None) -> str:
    text = _load(language())["strings"].get(key) or key
    for name, value in (args or {}).items():
        text = text.replace("{" + name + "}", str(value))
    return text


def fmt_num(value: float, decimals: int) -> str:
    meta = _load(language()).get("meta", {})
    decimal, group = meta.get("decimal", ","), meta.get("group", ".")
    s = f"{abs(value):.{decimals}f}"
    whole, _, frac = s.partition(".")
    grouped = ""
    for i, ch in enumerate(whole):
        if i and (len(whole) - i) % 3 == 0:
            grouped += group
        grouped += ch
    negative = value < 0 and abs(value) >= 0.5 * 10 ** (-decimals)
    return ("-" if negative else "") + grouped + (decimal + frac if frac else "")


def bundle(code: str) -> dict[str, Any]:
    lang = code if is_language(code) else "hr"
    languages = {c: _load(c).get("meta", {}).get("name", c) for c in LANGUAGES}
    data = _load(lang)
    return {"lang": lang, "meta": data.get("meta", {}), "strings": data.get("strings", {}), "languages": languages}
