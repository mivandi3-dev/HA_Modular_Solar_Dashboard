"""Stanje poslužitelja: postavke, baza, prognoza, slike, poller – zajedničko za API i poller."""
from __future__ import annotations

import os
import secrets
import threading
from pathlib import Path
from typing import Any

from . import VERSION, ha_api
from .config import SettingsStore, settings_from_json, to_form
from .data import DataService
from .devices import PlantReading, device_capabilities
from .ha_sensors import HaSensors
from .images import KINDS, Images
from .netinfo import default_route_interface, list_interfaces
from .poller import Poller
from .serialio import list_serial_ports
from .storage import Db
from .util import local_date, log, now, write_atomic
from .vendors import profiles_json
from .weather import WeatherService

UI_KEYS = ("theme", "palette", "icon_theme", "design", "hero_photo", "plant_name", "location", "commissioned", "speedo_max_kw",
           "peak_power_kwp", "co2_factor", "meter_unit_id", "poll_interval_s", "hide_idle_cursor", "headline", "language",
           "device_type", "headline_running", "headline_idle", "currency", "price_kwh", "feedin_price_kwh", "night_mode",
           "night_from", "night_to", "forecast_days")


class Core:
    def __init__(self, data_dir: Path, assets_dir: Path, token_file: Path | None = None, api_token: str = "",
                 publish_sensors: bool = True, ha_notify: str = "", compact_after_days: int = 0,
                 mqtt: dict[str, Any] | None = None) -> None:
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_file = data_dir / "solar.db"
        self.store = SettingsStore(data_dir)
        self._lock = threading.Lock()
        self._settings = self.store.load()
        Db(self.db_file).close()  # shema i WAL odmah
        self.data = DataService(self.db_file)
        self.weather = WeatherService()
        self.images = Images(data_dir / "images", assets_dir)
        self.ha_notify = ha_notify.strip()  # "persistent_notification" ili "notify.<usluga>" – obavijesti u HA
        self.compact_after_days = max(0, compact_after_days)
        self.mqtt = None
        if publish_sensors and mqtt and mqtt.get("host"):
            try:
                from .ha_mqtt import HaMqtt

                self.mqtt = HaMqtt(mqtt["host"], int(mqtt.get("port") or 1883), mqtt.get("user", ""), mqtt.get("password", ""))
            except Exception as e:  # noqa: BLE001 – senzori nisu nužni za bilježenje
                log.warning("MQTT nije dostupan (%s) – senzori idu preko Home Assistant API-ja", e)
        self.sensors = HaSensors(publish_sensors and self.mqtt is None)
        self.api_token = api_token or self._load_token(token_file)
        self.poller = Poller(self)

    # ------------------------------------------------------------ pristupni ključ API-ja
    def _load_token(self, token_file: Path | None) -> str:
        own = self.data_dir / "api_token"
        try:
            token = own.read_text().strip()
        except OSError:
            token = ""
        if len(token) < 32:
            token = secrets.token_urlsafe(32)
            write_atomic(own, token, private=True)
            log.info("Izrađen novi pristupni ključ API-ja (%s)", own)
        if token_file:  # dashboard add-on ga čita iz /share – bez ručnog kopiranja
            try:
                if not token_file.exists() or token_file.read_text().strip() != token:
                    write_atomic(token_file, token, private=True)
            except OSError as e:
                log.warning("Pristupni ključ nije zapisan u %s: %s", token_file, e)
        return token

    # ------------------------------------------------------------ postavke
    def settings(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._settings)

    def configured(self) -> bool:
        return self.store.exists()

    def apply_settings(self, s: dict[str, Any]) -> None:
        s = settings_from_json(s)
        with self._lock:
            self.store.save(s)
            self._settings = s
        log.info("Postavke spremljene")
        self.poller.settings_changed()

    # ------------------------------------------------------------ podaci
    def ui_settings(self, s: dict[str, Any]) -> dict[str, Any]:
        out = {k: s[k] for k in UI_KEYS}
        has_meter = bool(s["ha_grid_entity"]) if s["device_type"] == "homeassistant" else bool(s["meter_unit_id"])
        out["meter_unit_id"] = 1 if has_meter else 0  # SMA-08: bez tehničkih postavki (adrese)
        return out

    def dashboard(self) -> dict[str, Any]:
        s = self.settings()
        d = self.data.dashboard(s)
        d["settings"] = self.ui_settings(s)
        d["weather"] = self.weather.get(s)
        d["images"] = {k: self.images.url(k) for k in KINDS}
        d["version"] = VERSION
        d["capabilities"] = device_capabilities(s)
        return d

    def state(self) -> dict[str, Any]:
        """Sve što obrazac postavki treba od poslužitelja (get_state u bridge.cpp, bez Windows dijelova)."""
        s = self.settings()
        return {
            "version": VERSION, "wizard": not self.configured(), "settings": to_form(s), "interfaces": list_interfaces(),
            "suggested": {"logger": "", "internet": default_route_interface() or ""},
            "db": self.data.db_info(), "device_profiles": profiles_json(), "serial_ports": list_serial_ports(),
            "device_types": ["logger", "inverter", "sunspec", "fronius", "vendor", "voltronic", "vedirect"]
                            + (["homeassistant"] if ha_api.available() else []),
            "images": {k: self.images.info(k) for k in KINDS}, "capabilities": device_capabilities(s),
            "poller": {"last_ok": self.poller.last_ok, "last_error": self.poller.last_error, "failures": self.poller.failures},
            "paths": {"config": str(self.store.config_file), "data": str(self.data_dir), "logs": "Home Assistant → add-on → Log"},
        }

    def sensor_values(self, plant: PlantReading) -> dict[str, Any]:
        with Db(self.db_file) as db:
            last = db.latest()
        values: dict[str, Any] = {"power_kw": plant.reading.power_kw, "load_kw": plant.load_kw}
        if last:
            values.update({"day_kwh": last.e_daily_kwh, "total_kwh": last.e_total_kwh})
        values.update({k: plant.extra.get(k) for k in ("battery_soc", "battery_kw", "inverter_temp", "grid_v", "grid_hz", "ac_load_kw")})
        return values

    def publish_sensors(self, plant: PlantReading | None) -> None:
        if self.mqtt:
            if plant is not None:
                values = self.sensor_values(plant)
                today = local_date(now())
                values["month_kwh"] = sum(d.kwh for d in self.data.daily(today.replace(day=1), today))
                s = self.settings()
                self.mqtt.publish(values, {"identifiers": ["solarni_monitor"], "name": s["plant_name"] or "Solarna elektrana",
                                           "manufacturer": "Solarni monitor", "model": s["device_type"], "sw_version": VERSION})
            return
        if not self.sensors.enabled:
            return
        if plant is None:
            self.sensors.publish({"power_kw": 0}, False)
            return
        self.sensors.publish(self.sensor_values(plant), True)

    def close(self) -> None:
        if self.mqtt:
            self.mqtt.close()


def env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))
