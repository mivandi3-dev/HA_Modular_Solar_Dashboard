"""Raspored widgeta (layout.cpp): mreža 12 × 5, do 6 stranica koje se izmjenjuju, katalog iz web/catalog.json."""
from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .i18n import tr
from .util import read_json, write_json

MAX_PAGES = 6
ROTATE_CHOICES = (0, 10, 15, 20, 30, 45, 60, 120, 300)
_ID = re.compile(r"^[a-z0-9_-]{1,40}$")


@dataclass
class Option:
    key: str
    kind: str
    label: str
    default: Any
    choices: list[Any]
    max_len: int = 80


@dataclass
class Spec:
    key: str
    title: str
    min_w: int
    min_h: int
    max_w: int
    max_h: int
    options: list[Option] = field(default_factory=list)


class Catalog:
    def __init__(self, file: Path) -> None:
        self.raw = json.loads(file.read_text(encoding="utf-8"))
        self.cols = self.raw.get("cols", 12)
        self.rows = self.raw.get("rows", 5)
        self.default_layout = self.raw.get("defaultLayout", [])
        self.widgets: dict[str, Spec] = {}
        for w in self.raw["widgets"]:
            opts = [Option(o["key"], o["kind"], o.get("label", ""), o["default"], [c[0] for c in o.get("choices", [])],
                           o.get("maxLen", 80)) for o in w.get("options", [])]
            self.widgets[w["key"]] = Spec(w["key"], w["title"], w["minSize"][0], w["minSize"][1], w["maxSize"][0],
                                          w["maxSize"][1], opts)


def _overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def _coerce_options(spec: Spec, raw: Any, errors: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for opt in spec.options:
        value = raw[opt.key] if isinstance(raw, dict) and opt.key in raw else opt.default
        if opt.kind == "choice":
            match = next((c for c in opt.choices if str(c) == str(value)), None)  # preglednik može poslati "14" umjesto 14
            if match is None:
                errors.append(tr("{widget}: neispravna vrijednost za „{option}“.", {"widget": tr(spec.title), "option": tr(opt.label)}))
                value = opt.default
            else:
                value = match
        else:
            value = (value if isinstance(value, str) else json.dumps(value)).strip()[: opt.max_len]
        out[opt.key] = value
    return out


def _int(v: Any) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not float(v).is_integer():
        raise ValueError
    return int(v)


def validate_layout(cat: Catalog, items: Any) -> tuple[list[dict[str, Any]], list[str]]:
    out: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    if not isinstance(items, list):
        return out, errors
    for raw in items:
        spec = cat.widgets.get(raw.get("type")) if isinstance(raw, dict) and isinstance(raw.get("type"), str) else None
        try:
            if not spec:
                raise ValueError
            p = {"id": raw["id"] if isinstance(raw.get("id"), str) else f"{spec.key}-{secrets.token_hex(3)}", "type": spec.key,
                 "x": _int(raw["x"]), "y": _int(raw["y"]), "w": _int(raw["w"]), "h": _int(raw["h"])}
        except (KeyError, ValueError, TypeError):
            errors.append(tr("Nepoznat ili oštećen widget."))
            continue
        problem = ""
        if not _ID.match(p["id"]) or p["id"] in seen:
            problem = tr("neispravna oznaka")
        elif not (spec.min_w <= p["w"] <= spec.max_w and spec.min_h <= p["h"] <= spec.max_h):
            problem = tr("veličina {size} nije dopuštena (od {min} do {max})",
                         {"size": f"{p['w']}×{p['h']}", "min": f"{spec.min_w}×{spec.min_h}", "max": f"{spec.max_w}×{spec.max_h}"})
        elif p["x"] < 0 or p["y"] < 0 or p["x"] > cat.cols - p["w"] or p["y"] > cat.rows - p["h"]:
            problem = tr("izlazi iz ekrana")
        p["options"] = _coerce_options(spec, raw.get("options", {}), errors)
        if not problem and any(_overlaps(p, o) for o in out):
            problem = tr("preklapa se s drugim widgetom")
        if problem:
            errors.append(f"{tr(spec.title)}: {problem}.")
            continue
        seen.add(p["id"])
        out.append(p)
    return out, errors


class Layout:
    def __init__(self, cat: Catalog, file: Path) -> None:
        self.cat, self.file = cat, file

    def load(self) -> dict[str, Any]:
        fallback = {"pages": [validate_layout(self.cat, self.cat.default_layout)[0]], "rotate_s": 0}
        j = read_json(self.file)
        if not isinstance(j, dict):
            return fallback
        raw_pages = ([p.get("widgets", []) if isinstance(p, dict) else [] for p in j["pages"]]
                     if isinstance(j.get("pages"), list) else [j.get("widgets", [])])
        rotate = j.get("rotate_s", 0)
        pages: list[list[dict[str, Any]]] = []
        seen: set[str] = set()  # oznaka widgeta jedinstvena je na svim stranicama
        for raw in raw_pages[:MAX_PAGES]:
            items = [p for p in validate_layout(self.cat, raw)[0] if p["id"] not in seen]
            seen.update(p["id"] for p in items)
            pages.append(items)
        return {"pages": pages or fallback["pages"], "rotate_s": rotate if rotate in ROTATE_CHOICES else 0}

    def save(self, pages: dict[str, Any]) -> None:
        write_json(self.file, {"version": 2, "rotate_s": pages["rotate_s"], "pages": [{"widgets": p} for p in pages["pages"]]})

    @staticmethod
    def as_json(pages: dict[str, Any]) -> dict[str, Any]:
        return {"pages": pages["pages"], "rotateS": pages["rotate_s"]}

    def save_page(self, items: list[dict[str, Any]], page: int) -> None:
        pages = self.load()
        if page == len(pages["pages"]) and page < MAX_PAGES:
            pages["pages"].append([])
        if not 0 <= page < len(pages["pages"]):
            raise RuntimeError(tr("Stranica ne postoji."))
        ids = {it["id"] for it in items}
        for n, other in enumerate(pages["pages"]):
            if n != page and any(o["id"] in ids for o in other):
                raise RuntimeError(tr("Oznaka widgeta već postoji na drugoj stranici."))
        pages["pages"][page] = items
        self.save(pages)

    def remove_page(self, page: int) -> dict[str, Any]:
        pages = self.load()
        if len(pages["pages"]) > 1 and 0 <= page < len(pages["pages"]):
            del pages["pages"][page]
            self.save(pages)
        return pages

    def set_rotation(self, seconds: int) -> dict[str, Any]:
        if seconds not in ROTATE_CHOICES:
            raise RuntimeError(tr("Nepoznat interval izmjene."))
        pages = self.load()
        pages["rotate_s"] = seconds
        self.save(pages)
        return pages

    def reset(self) -> dict[str, Any]:
        try:
            self.file.unlink()
        except FileNotFoundError:
            pass
        return self.load()
