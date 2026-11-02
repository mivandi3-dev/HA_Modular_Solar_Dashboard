"""Zamjenjive slike (images.cpp): fotografija u zaglavlju (6 : 1), crtež zgrade (16 : 9) i logotip – Pillow umjesto WIC-a."""
from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .i18n import tr

MAX_FILE_BYTES = 40 * 1024 * 1024
RATIO_TOLERANCE = 0.15
THUMB_WIDTH = 360
KINDS = ("hero", "drawing", "logo")


@dataclass(frozen=True)
class Spec:
    title: str
    ratio: float
    ratio_text: str
    min_w: int
    min_h: int
    max_w: int
    hint: str
    custom_name: str
    default_name: str


SPECS = {
    "hero": Spec("Fotografija u zaglavlju", 6.0, "6 : 1", 1920, 320, 3840,
                 "Široka fotografija, omjer 6 : 1 – npr. 3840 × 640 px (za 4K) ili najmanje 1920 × 320 px. Lijeva trećina "
                 "prekrivena je pozdravom i logom, a desno je prognoza, pa glavni motiv (zgrada) neka bude u sredini. Šira ili "
                 "viša slika automatski se obreže po sredini.", "hero.jpg", "zgrada_iz_zraka.jpg"),
    "drawing": Spec("Crtež zgrade (Tok energije)", 16 / 9, "16 : 9", 960, 540, 2400,
                    "Crtež ili fotografija zgrade, omjer 16 : 9 – npr. 1920 × 1080 px. Zgrada u sredini, a pozadina jednolična i "
                    "svijetla (aplikacija je sama ukloni) ili PNG s prozirnom pozadinom.", "drawing.png", "crtez.png"),
    "logo": Spec("Logotip tvrtke", 9.0, "široki, npr. 9 : 1", 300, 30, 1840,
                 "PNG s prozirnom pozadinom, širok i nizak – npr. 1840 × 200 px (najmanje 920 px širine za oštar prikaz na 4K). "
                 "Prikazuje se u kartici zaglavlja širine 356 px i visine najviše 96 px; uži ili viši logotip se smanji da stane, "
                 "bez obrezivanja.", "logo.png", "logo.png"),
}

CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class Images:
    def __init__(self, images_dir: Path, assets_dir: Path) -> None:
        self.images_dir = images_dir
        self.assets_dir = assets_dir

    def path(self, kind: str) -> Path:
        custom = self.images_dir / SPECS[kind].custom_name
        return custom if custom.exists() else self.assets_dir / SPECS[kind].default_name

    def version(self, kind: str) -> int:
        try:
            return int(self.path(kind).stat().st_mtime_ns // 1000)
        except OSError:
            return 0

    def url(self, kind: str) -> str:
        return f"/api/v1/images/{kind}?v={self.version(kind)}"

    def is_custom(self, kind: str) -> bool:
        return self.path(kind).parent == self.images_dir

    def info(self, kind: str) -> dict[str, Any]:
        s, p = SPECS[kind], self.path(kind)
        out: dict[str, Any] = {"kind": kind, "title": s.title, "hint": s.hint, "ratio": s.ratio_text, "custom": self.is_custom(kind),
                               "path": str(p), "width": 0, "height": 0, "thumb": ""}
        try:
            from PIL import Image

            with Image.open(p) as im:
                out["width"], out["height"] = im.size
                w = min(THUMB_WIDTH, im.width)
                thumb = im.convert("RGBA").resize((w, max(1, round(im.height * w / im.width))))
                buf = io.BytesIO()
                thumb.save(buf, "PNG")
                out["thumb"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        except (OSError, ValueError):
            pass  # slika nedostaje – sučelje to javlja
        return out

    def replace(self, kind: str, data: bytes) -> dict[str, Any]:
        from PIL import Image, UnidentifiedImageError

        s = SPECS[kind]
        if len(data) > MAX_FILE_BYTES:
            raise RuntimeError(tr("Slika je veća od {mb} MB.", {"mb": 40}))
        try:
            im = Image.open(io.BytesIO(data))
            im.load()
        except (UnidentifiedImageError, OSError) as e:
            raise RuntimeError(tr("Datoteka nije slika (podržano: JPG, PNG, WebP).")) from e
        if im.width < s.min_w or im.height < s.min_h:
            raise RuntimeError(tr("Slika je premala ({w} × {h} px); najmanje {mw} × {mh} px.",
                                  {"w": im.width, "h": im.height, "mw": s.min_w, "mh": s.min_h}))
        w, h = im.size
        if w > s.max_w:
            h, w = round(h * s.max_w / w), s.max_w
            im = im.resize((w, h), Image.LANCZOS)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        target = self.images_dir / s.custom_name
        tmp = target.with_suffix(target.suffix + ".tmp")
        if kind == "hero":
            im.convert("RGB").save(tmp, "JPEG", quality=92)
        else:  # crtež i logotip ostaju PNG (čuva prozirnost)
            im.convert("RGBA").save(tmp, "PNG")
        os.replace(tmp, target)
        ratio = w / h
        message = tr("Slika je promijenjena ({w} × {h} px).", {"w": w, "h": h})
        if kind == "logo":
            if ratio < 3:
                message += " " + tr("Logotip je visok – bit će smanjen na visinu kartice (preporučen je širi logotip).")
        elif abs(ratio - s.ratio) / s.ratio > RATIO_TOLERANCE:
            message += " " + tr("Omjer slike je {ratio} : 1, a preporučeno je {wanted}.", {"ratio": f"{ratio:.2f}", "wanted": tr(s.ratio_text)})
            if kind == "hero":
                message += " " + tr("Dio slike bit će obrezan.")
        info = self.info(kind)
        info["message"] = message
        return info

    def reset(self, kind: str) -> None:
        try:
            (self.images_dir / SPECS[kind].custom_name).unlink()
        except FileNotFoundError:
            pass

    def content_type(self, kind: str) -> str:
        return CONTENT_TYPES.get(self.path(kind).suffix.lower(), "application/octet-stream")
