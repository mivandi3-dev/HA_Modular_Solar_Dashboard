"""Bilježenje očitanja (poller.cpp): nit koja svakih poll_interval_s sekundi (poravnato) čita uređaj i upisuje u SQLite,
jednom dnevno radi sigurnosnu kopiju baze i šalje obavijesti e-poštom. Novo za HA: nakon očitanja objavljuje senzore
u Home Assistant (ha_sensors.py)."""
from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

from . import ha_api, i18n
from .alerts import Observation, evaluate_alerts, expected_until, load_state, save_state, wants_forecast
from .config import mail_configured
from .devices import PlantReading, read_plant, store_reading
from .mailer import send_mail
from .netinfo import source_ip
from .storage import Db, compact_history, daily_backup
from .util import local_date, log, now
from .weather import fetch as fetch_weather

if TYPE_CHECKING:
    from .core import Core

MIN_INTERVAL_S = 5
FORECAST_TTL_S = 3600


class Notifier:
    def __init__(self, core: "Core") -> None:
        self.core = core
        self.path = core.data_dir / "alerts.json"
        self.state = load_state(self.path)
        self.last_ok: int | None = None
        self.forecast_at = 0
        self.hourly: list[Any] = []
        try:
            with Db(core.db_file) as db:
                last = db.latest()
                self.last_ok = last.ts if last else None
        except Exception:  # noqa: BLE001
            pass

    def _expected(self, s: dict[str, Any], t: int) -> float | None:
        if not wants_forecast(s, self.state, t):
            return None
        if t - self.forecast_at > FORECAST_TTL_S:
            self.forecast_at = t
            try:
                self.hourly = fetch_weather(s["weather_lat"], s["weather_lon"], source_ip(s["internet_interface"])).get("hourly", [])
            except RuntimeError as e:
                log.warning("Prognoza za obavijesti nije dostupna: %s", e)
                self.hourly = []
        return expected_until(self.hourly, t, s["peak_power_kwp"]) if self.hourly else None

    def process(self, s: dict[str, Any], p: PlantReading | None, error: str) -> None:
        mail, ha = mail_configured(s), bool(self.core.ha_notify)
        if not mail and not ha:
            return
        t = now()
        if p:
            self.last_ok = t
        obs = Observation(t, p is not None, self.last_ok, error=error)
        if p:
            obs.status, obs.day_kwh, obs.expected_kwh = p.reading.status, p.reading.e_daily_kwh, self._expected(s, t)
        state, messages = evaluate_alerts(s, self.state, obs)
        if state != self.state:
            self.state = state
            try:
                save_state(self.path, state)
            except OSError as e:
                log.error("Stanje obavijesti nije spremljeno: %s", e)
        for m in messages:
            threading.Thread(target=self._send, args=(dict(s), m.subject, m.body, mail), daemon=True).start()

    def _send(self, s: dict[str, Any], subj: str, body: str, mail: bool) -> None:
        if mail:
            try:
                send_mail(s, subj, body)
            except Exception as e:  # noqa: BLE001
                log.warning("Obavijest „%s“ nije poslana: %s", subj, e)
        if self.core.ha_notify:  # i u Home Assistant (obavijest u HA ili push na mobitel)
            try:
                ha_api.notify(self.core.ha_notify, subj, body)
            except Exception as e:  # noqa: BLE001
                log.warning("Obavijest u Home Assistant „%s“ nije poslana: %s", subj, e)


class Poller:
    def __init__(self, core: "Core") -> None:
        self.core = core
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error = ""
        self.last_ok: int | None = None
        self.failures = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="poller", daemon=True)
        self._thread.start()

    def alive(self) -> bool:
        return self._thread is None or self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=15)

    def settings_changed(self) -> None:
        self._wake.set()  # odmah novo očitanje s novim postavkama

    def _sleep_aligned(self, interval: int) -> None:
        """Do sljedećeg višekratnika intervala (ravnomjerna očitanja); prekida ga promjena postavki."""
        wait = interval - time.time() % interval
        self._wake.wait(wait)
        self._wake.clear()

    def _run(self) -> None:
        notifier = Notifier(self.core)
        backup_day = None
        s = self.core.settings()
        log.info("Poller pokrenut: %s:%s (%s), svakih %s s", s["modbus_host"], s["modbus_port"], s["device_type"],
                 max(MIN_INTERVAL_S, s["poll_interval_s"]))
        while not self._stop.is_set():
            s = self.core.settings()
            i18n.set_default_language(s["language"])  # obavijesti na jeziku postavki
            i18n.set_language(None)
            today = local_date(now())
            if backup_day != today:
                backup_day = today
                try:
                    created = daily_backup(self.core.db_file, self.core.data_dir / "backups", s["backup_keep_days"], today)
                    if created:
                        log.info("Sigurnosna kopija baze: %s", created)
                except Exception as e:  # noqa: BLE001
                    log.error("Sigurnosna kopija baze nije uspjela: %s", e)
                if self.core.compact_after_days:
                    try:
                        with Db(self.core.db_file) as db:
                            removed = compact_history(db, self.core.compact_after_days, today)
                        if removed:
                            self.core.data.invalidate()
                            log.info("Sažeta stara povijest: %d očitanja manje (5-minutni prosjeci, dnevni vrh ostaje)", removed)
                    except Exception as e:  # noqa: BLE001
                        log.error("Sažimanje povijesti nije uspjelo: %s", e)
            if not self.core.configured():
                self._sleep_aligned(max(MIN_INTERVAL_S, s["poll_interval_s"]))
                continue
            plant: PlantReading | None = None
            error = ""
            try:
                plant = read_plant(s)
            except Exception as e:  # noqa: BLE001 – poller nikad ne smije stati
                error = str(e)
                log.warning("%s", error)
            if plant:
                if plant.meter_error:
                    log.warning("Mjerač (unit %s): %s", s["meter_unit_id"], plant.meter_error)
                try:
                    with Db(self.core.db_file) as db:
                        store_reading(db, plant)
                    if self.failures:
                        log.info("Uređaj ponovno dostupan nakon %d neuspjelih pokušaja", self.failures)
                    self.failures, self.last_ok, self.last_error = 0, now(), ""
                except Exception as e:  # noqa: BLE001
                    log.error("Upis u bazu nije uspio: %s", e)
                    plant = None
            else:
                self.failures += 1
                self.last_error = error
            try:
                notifier.process(s, plant, error)
            except Exception as e:  # noqa: BLE001 – obavijesti nikad ne smiju zaustaviti bilježenje
                log.error("Obavijesti: %s", e)
            try:
                self.core.publish_sensors(plant)
            except Exception as e:  # noqa: BLE001
                log.debug("Senzori za Home Assistant: %s", e)
            self._sleep_aligned(max(MIN_INTERVAL_S, s["poll_interval_s"]))
        log.info("Poller zaustavljen")
