"""Novo u HA verziji: senzori elektrane u Home Assistantu, bez ručnog YAML-a.

Kad poslužitelj radi kao add-on (SUPERVISOR_TOKEN + homeassistant_api), nakon svakog očitanja upisuje stanja preko
Supervisor API-ja (POST /core/api/states/<entity_id>). Senzori energije imaju state_class total_increasing i
device_class energy, pa se mogu dodati u HA Energy nadzornu ploču. Šalje se najviše jednom u 30 s i samo kad se
vrijednost promijeni (manje upisa u recorder HA-a)."""
from __future__ import annotations

import json
import os
import time
from typing import Any

from .netinfo import http_request
from .util import log

SUPERVISOR_URL = "http://supervisor/core/api/states/"
MIN_INTERVAL_S = 30

SENSORS: tuple[tuple[str, str, str, str | None, str | None], ...] = (
    # (ključ, naziv, jedinica, device_class, state_class)
    ("power_kw", "Solarna elektrana – snaga", "kW", "power", "measurement"),
    ("day_kwh", "Solarna elektrana – danas", "kWh", "energy", "total_increasing"),
    ("total_kwh", "Solarna elektrana – ukupno", "kWh", "energy", "total_increasing"),
    ("load_kw", "Solarna elektrana – mreža (uzimanje +)", "kW", "power", "measurement"),
    ("battery_soc", "Solarna elektrana – baterija", "%", "battery", "measurement"),
    ("battery_kw", "Solarna elektrana – snaga baterije", "kW", "power", "measurement"),
    ("inverter_temp", "Solarna elektrana – temperatura invertera", "°C", "temperature", "measurement"),
    ("grid_v", "Solarna elektrana – napon mreže", "V", "voltage", "measurement"),
)


class HaSensors:
    def __init__(self, enabled: bool, prefix: str = "solarni") -> None:
        self.token = os.environ.get("SUPERVISOR_TOKEN", "")
        self.enabled = enabled and bool(self.token)
        self.prefix = prefix
        self._last: dict[str, Any] = {}
        self._at = 0.0

    def publish(self, values: dict[str, Any], available: bool) -> None:
        if not self.enabled or time.time() - self._at < MIN_INTERVAL_S:
            return
        self._at = time.time()
        for key, name, unit, device_class, state_class in SENSORS:
            if key not in values or values[key] is None:
                continue
            state = round(float(values[key]), 3) if available else "unavailable"
            if self._last.get(key) == state:
                continue
            attrs = {"friendly_name": name, "unit_of_measurement": unit, "icon": "mdi:solar-power"}
            if device_class:
                attrs["device_class"] = device_class
            if state_class:
                attrs["state_class"] = state_class
            try:
                status, _ = http_request(SUPERVISOR_URL + f"sensor.{self.prefix}_{key}", 5, None, "POST",
                                         json.dumps({"state": state, "attributes": attrs}).encode(),
                                         {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
                if status < 300:
                    self._last[key] = state
            except OSError as e:
                log.debug("HA senzor %s: %s", key, e)
