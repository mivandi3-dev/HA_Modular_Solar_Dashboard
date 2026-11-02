"""MQTT discovery (Mosquitto add-on): elektrana kao **uređaj** u Home Assistantu s entitetima koji imaju unique_id (mogu
se preimenovati, dodijeliti prostoriji, koristiti u Energy nadzornoj ploči). Stanja idu na jednu temu kao JSON
(solarni/<id>/state), dostupnost na solarni/<id>/status (oporuka „offline” kad poslužitelj stane).

Kad je MQTT dostupan, koristi se umjesto izravnog upisa stanja preko REST API-ja (ha_sensors.py)."""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from .util import log

DISCOVERY_PREFIX = "homeassistant"
MIN_INTERVAL_S = 10

# (ključ, naziv, jedinica, device_class, state_class, ikona)
SENSORS: tuple[tuple[str, str, str | None, str | None, str | None, str], ...] = (
    ("power_kw", "Snaga", "kW", "power", "measurement", "mdi:solar-power"),
    ("day_kwh", "Proizvodnja danas", "kWh", "energy", "total_increasing", "mdi:solar-power-variant"),
    ("month_kwh", "Proizvodnja ovaj mjesec", "kWh", "energy", "total", "mdi:calendar-month"),
    ("total_kwh", "Ukupna proizvodnja", "kWh", "energy", "total_increasing", "mdi:counter"),
    ("load_kw", "Mreža (uzimanje +, predaja −)", "kW", "power", "measurement", "mdi:transmission-tower"),
    ("battery_soc", "Baterija", "%", "battery", "measurement", "mdi:battery"),
    ("battery_kw", "Snaga baterije (punjenje +)", "kW", "power", "measurement", "mdi:battery-charging"),
    ("inverter_temp", "Temperatura invertera", "°C", "temperature", "measurement", "mdi:thermometer"),
    ("grid_v", "Napon mreže", "V", "voltage", "measurement", "mdi:sine-wave"),
    ("grid_hz", "Frekvencija mreže", "Hz", "frequency", "measurement", "mdi:sine-wave"),
    ("ac_load_kw", "Potrošnja off-grid izlaza", "kW", "power", "measurement", "mdi:home-lightning-bolt"),
)


class HaMqtt:
    def __init__(self, host: str, port: int, user: str, password: str, node_id: str = "solarni") -> None:
        self.node_id = node_id
        self.base = f"solarni/{node_id}"
        self.connected = threading.Event()
        self._announced: set[str] = set()
        self._at = 0.0
        self._device: dict[str, Any] = {}
        try:
            import paho.mqtt.client as mqtt
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("paho-mqtt nije instaliran") from e
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"solarni-server-{node_id}")
        if user:
            self.client.username_pw_set(user, password)
        self.client.will_set(f"{self.base}/status", "offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = lambda *_a, **_k: self.connected.clear()
        self.client.reconnect_delay_set(2, 60)
        self.client.connect_async(host, port, keepalive=60)
        self.client.loop_start()
        log.info("MQTT: spajam se na %s:%s", host, port)

    def _on_connect(self, client: Any, _userdata: Any, _flags: Any, reason: Any, _props: Any = None) -> None:
        if getattr(reason, "is_failure", False):
            log.warning("MQTT: veza odbijena (%s)", reason)
            return
        self.connected.set()
        self._announced.clear()  # nakon ponovnog spajanja (npr. restart brokera) discovery se šalje iznova
        client.publish(f"{self.base}/status", "online", qos=1, retain=True)
        log.info("MQTT: spojen")

    def _announce(self, key: str, name: str, unit: str | None, device_class: str | None, state_class: str | None, icon: str) -> None:
        cfg: dict[str, Any] = {
            "name": name, "unique_id": f"{self.node_id}_{key}", "object_id": f"{self.node_id}_{key}",
            "state_topic": f"{self.base}/state", "value_template": f"{{{{ value_json.{key} }}}}",
            "availability_topic": f"{self.base}/status", "device": self._device, "icon": icon,
        }
        if unit:
            cfg["unit_of_measurement"] = unit
        if device_class:
            cfg["device_class"] = device_class
        if state_class:
            cfg["state_class"] = state_class
        self.client.publish(f"{DISCOVERY_PREFIX}/sensor/{self.node_id}/{key}/config", json.dumps(cfg), qos=1, retain=True)
        self._announced.add(key)

    def publish(self, values: dict[str, Any], device: dict[str, Any]) -> None:
        if not self.connected.is_set() or time.time() - self._at < MIN_INTERVAL_S:
            return
        self._at = time.time()
        if device != self._device:
            self._device = device
            self._announced.clear()
        for key, *rest in SENSORS:
            if values.get(key) is not None and key not in self._announced:
                self._announce(key, *rest)  # entitet tek kad uređaj daje tu vrijednost (npr. baterija)
        state = {k: round(float(v), 3) for k, v in values.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
        self.client.publish(f"{self.base}/state", json.dumps(state), qos=0, retain=True)

    def close(self) -> None:
        try:
            self.client.publish(f"{self.base}/status", "offline", qos=1, retain=True)
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:  # noqa: BLE001
            pass
