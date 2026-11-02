"""Home Assistant REST API – kao add-on preko Supervisora (SUPERVISOR_TOKEN, http://supervisor/core/api), samostalno uz
SOLARI_HA_URL (npr. http://homeassistant.local:8123) i dugotrajni pristupni ključ SOLARI_HA_TOKEN.

Koristi se za: stanja entiteta (vrsta uređaja „Home Assistant entiteti”), senzore (states) i obavijesti (services)."""
from __future__ import annotations

import json
import os
from typing import Any

from .i18n import tr
from .netinfo import http_request

TIMEOUT_S = 8


def _base() -> tuple[str, str]:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if token:
        return "http://supervisor/core/api", token
    return os.environ.get("SOLARI_HA_URL", "").rstrip("/") + "/api", os.environ.get("SOLARI_HA_TOKEN", "")


def available() -> bool:
    url, token = _base()
    return bool(token) and url != "/api"


def request(method: str, path: str, body: Any = None) -> tuple[int, Any]:
    url, token = _base()
    if not available():
        raise RuntimeError(tr("Home Assistant API nije dostupan (poslužitelj ne radi kao add-on, a SOLARI_HA_URL/SOLARI_HA_TOKEN nisu postavljeni)."))
    try:
        status, raw = http_request(url + path, TIMEOUT_S, None, method, json.dumps(body).encode() if body is not None else None,
                                   {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    except OSError as e:
        raise RuntimeError(tr("Home Assistant ne odgovara: {error}", {"error": e})) from e
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, None


def state(entity_id: str) -> dict[str, Any]:
    status, body = request("GET", f"/states/{entity_id}")
    if status == 404:
        raise RuntimeError(tr("Entitet {entity} ne postoji u Home Assistantu.", {"entity": entity_id}))
    if status != 200 or not isinstance(body, dict):
        raise RuntimeError(tr("Home Assistant je vratio grešku {code}.", {"code": status}))
    return body


def call_service(domain: str, service: str, data: dict[str, Any]) -> None:
    status, _ = request("POST", f"/services/{domain}/{service}", data)
    if status >= 300:
        raise RuntimeError(tr("Home Assistant je vratio grešku {code}.", {"code": status}))


def notify(target: str, title: str, message: str) -> None:
    """target: "persistent_notification" (obavijest u HA) ili "notify.<usluga>" (npr. notify.mobile_app_mobitel)."""
    if target == "persistent_notification":
        call_service("persistent_notification", "create", {"title": title, "message": message, "notification_id": "solarni_monitor"})
        return
    domain, _, service = target.partition(".")
    if domain != "notify" or not service:
        raise RuntimeError(tr("Neispravna usluga obavijesti: {target}", {"target": target}))
    call_service("notify", service, {"title": title, "message": message})
