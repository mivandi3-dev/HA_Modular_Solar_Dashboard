"""HA optimizacije: entiteti HA kao izvor, MQTT discovery, obavijesti u HA, sažimanje povijesti, watchdog."""
import datetime as dt
import json

import pytest

from solari_server import config, ha_api
from solari_server.data import days_from_aggregates
from solari_server.devices import device_capabilities, read_plant
from solari_server.storage import Db, Reading, compact_history
from solari_server.util import local_midnight


def ts(day, seconds):
    return local_midnight(day) + seconds


# ---------------------------------------------------------------- entiteti Home Assistanta
STATES = {
    "sensor.pv_power": {"state": "3450", "attributes": {"unit_of_measurement": "W"}},
    "sensor.pv_today": {"state": "12.5", "attributes": {"unit_of_measurement": "kWh"}},
    "sensor.pv_total": {"state": "45.2", "attributes": {"unit_of_measurement": "MWh"}},
    "sensor.grid": {"state": "-1.2", "attributes": {"unit_of_measurement": "kW"}},
    "sensor.soc": {"state": "77", "attributes": {"unit_of_measurement": "%"}},
    "sensor.bat": {"state": "500", "attributes": {"unit_of_measurement": "W"}},
    "sensor.dead": {"state": "unavailable", "attributes": {}},
}


@pytest.fixture
def fake_ha(monkeypatch):
    def state(entity):
        if entity not in STATES:
            raise RuntimeError("ne postoji")
        return STATES[entity]

    monkeypatch.setattr(ha_api, "state", state)


def ha_settings(**kw):
    base = {"device_type": "homeassistant", "ha_power_entity": "sensor.pv_power", "ha_today_entity": "sensor.pv_today",
            "ha_total_entity": "sensor.pv_total", "ha_grid_entity": "sensor.grid", "ha_battery_soc_entity": "sensor.soc",
            "ha_battery_power_entity": "sensor.bat"}
    return config.settings_from_json({**base, **kw})


def test_ha_entities_units_and_battery(fake_ha):
    p = read_plant(ha_settings())
    assert p.reading.power_kw == pytest.approx(3.45)
    assert p.reading.e_daily_kwh == pytest.approx(12.5)
    assert p.reading.e_total_kwh == pytest.approx(45200)
    assert p.load_kw == pytest.approx(-1.2)
    assert p.extra == {"battery_soc": 77.0, "battery_kw": 0.5, "battery_dir": True}
    assert read_plant(ha_settings(meter_invert=True)).load_kw == pytest.approx(1.2)
    assert "battery" in device_capabilities(ha_settings())


def test_ha_entities_missing_values(fake_ha):
    p = read_plant(ha_settings(ha_today_entity="", ha_total_entity="", ha_grid_entity="sensor.dead"))
    assert p.reading.e_daily_kwh < 0 and p.reading.e_total_kwh < 0  # poller računa iz snage
    assert p.meter_error
    with pytest.raises(RuntimeError):
        read_plant(ha_settings(ha_power_entity="sensor.dead"))


def test_ha_entity_validation():
    cur = config.settings_from_json({})
    base = {"plant_name": "X", "headline": "Y", "currency": "€", "device_type": "homeassistant", "modbus_host": ""}
    _, errors = config.validate_form(base, cur, [])
    assert "ha_power_entity" in errors and "modbus_host" not in errors
    _, errors = config.validate_form({**base, "ha_power_entity": "Senzor snage"}, cur, [])
    assert "ha_power_entity" in errors
    new, errors = config.validate_form({**base, "ha_power_entity": "sensor.pv_power"}, cur, [])
    assert not errors and new["ha_power_entity"] == "sensor.pv_power"


def test_notify_targets(monkeypatch):
    calls = []
    monkeypatch.setattr(ha_api, "call_service", lambda d, s, data: calls.append((d, s, data)))
    ha_api.notify("persistent_notification", "Naslov", "Tekst")
    ha_api.notify("notify.mobile_app_mobitel", "Naslov", "Tekst")
    assert calls[0][:2] == ("persistent_notification", "create") and calls[1][:2] == ("notify", "mobile_app_mobitel")
    with pytest.raises(RuntimeError):
        ha_api.notify("light.kuhinja", "a", "b")


# ---------------------------------------------------------------- MQTT discovery
class FakeClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, retain))


def test_mqtt_discovery_and_state():
    from solari_server.ha_mqtt import HaMqtt

    m = HaMqtt.__new__(HaMqtt)  # bez stvarnog brokera
    m.node_id, m.base, m._announced, m._at, m._device = "solarni", "solarni/solarni", set(), 0.0, {}
    m.client = FakeClient()
    import threading

    m.connected = threading.Event()
    m.connected.set()
    device = {"identifiers": ["solarni_monitor"], "name": "Elektrana"}
    m.publish({"power_kw": 3.21, "day_kwh": 10.0, "battery_soc": None, "load_kw": -0.5}, device)
    topics = {t: p for t, p, _ in m.client.published}
    cfg = json.loads(topics["homeassistant/sensor/solarni/day_kwh/config"])
    assert cfg["unique_id"] == "solarni_day_kwh" and cfg["state_class"] == "total_increasing" and cfg["device"] == device
    assert "homeassistant/sensor/solarni/battery_soc/config" not in topics  # bez baterije nema entiteta
    assert json.loads(topics["solarni/solarni/state"]) == {"power_kw": 3.21, "day_kwh": 10.0, "load_kw": -0.5}
    n = len(m.client.published)
    m.publish({"power_kw": 1}, device)
    assert len(m.client.published) == n  # najviše jednom u 10 s


# ---------------------------------------------------------------- sažimanje povijesti
def test_compact_history_keeps_daily_energy_and_peak(tmp_path):
    db = Db(tmp_path / "solar.db")
    day = dt.date(2025, 5, 1)
    for i in range(0, 24 * 3600, 10):  # očitanje svakih 10 s
        hour = i / 3600
        kw = max(0.0, 5 - abs(hour - 12)) if 6 <= hour <= 18 else 0.0
        if i == 12 * 3600 + 10:
            kw = 9.9  # kratki vrh
        db.insert(ts(day, i), Reading(power_kw=kw, e_daily_kwh=round(i / 3600, 3), e_total_kwh=1000 + i / 3600), 1.0, {"battery_soc": 50})
    before = days_from_aggregates(db.hourly_aggregates(ts(day, 0), ts(day, 86400)), day, day)[0]
    removed = compact_history(db, 30, dt.date(2025, 7, 1))
    assert removed > 8000
    assert db.count_between(ts(day, 0), ts(day, 86400)) <= 24 * 12 + 1
    after = days_from_aggregates(db.hourly_aggregates(ts(day, 0), ts(day, 86400)), day, day)[0]
    assert after.kwh == pytest.approx(before.kwh)
    assert after.load == pytest.approx(before.load, rel=0.02)
    assert db.peak_power_between(ts(day, 0), ts(day, 86400))[1] == pytest.approx(9.9)  # dnevni vrh ostaje
    assert compact_history(db, 30, dt.date(2025, 7, 1)) == 0  # već obrađeno (user_version)
    assert compact_history(db, 0, dt.date(2025, 7, 1)) == 0


def test_compact_skips_recent_days(tmp_path):
    db = Db(tmp_path / "solar.db")
    day = dt.date(2025, 6, 25)
    for i in range(0, 3600, 10):
        db.insert(ts(day, i), Reading(power_kw=1, e_daily_kwh=0, e_total_kwh=1), None)
    assert compact_history(db, 30, dt.date(2025, 7, 1)) == 0
    assert db.count_between(ts(day, 0), ts(day, 3600)) == 360
