"""Baza, izračuni dnevnih iznosa, postavke, obavijesti, izvještaj i uvoz SmartLoggera."""
import datetime as dt
import io
import struct
import zipfile

import pytest

from solari_server import config
from solari_server.alerts import AlertState, Observation, evaluate_alerts, expected_until
from solari_server.data import DataService, days_from_aggregates, savings
from solari_server.devices import PlantReading, daily_from_total, integrate_total, store_reading
from solari_server.report import build_report, report_csv
from solari_server.smartlogger import import_perfmg_days, parse_perfmg_day, read_perfmg_day
from solari_server.storage import Db, Reading
from solari_server.util import local_midnight


def ts(day, hour):
    return local_midnight(day) + hour * 3600


def sample_emap():
    def rec(device, kpi, day, value):
        t = int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp())
        return struct.pack("<HHIIi", device, kpi, 86400, t, value)

    d = dt.date
    return (bytes(8) + rec(2, 0x3011, d(2024, 6, 1), 59929) + rec(2, 0x3011, d(2024, 6, 2), 41000)
            + rec(2, 0x3011, d(2024, 6, 3), -1) + rec(3, 0x3011, d(2024, 6, 4), 500) + rec(2, 0x3011, d(2024, 6, 5), 0)
            + rec(2, 0x3011, d(2024, 6, 6), 12345) + rec(2, 0x3011, d(1970, 1, 2), 100))


def test_daily_from_total_and_integration(tmp_path):
    db = Db(tmp_path / "solar.db")
    day = dt.date(2026, 6, 10)
    assert daily_from_total(db, ts(day, 12), 1000) == 0.0
    db.insert(ts(day, 7), Reading(e_total_kwh=1005), None)
    assert daily_from_total(db, ts(day, 12), 1012.5) == pytest.approx(7.5)
    db.insert(ts(day, -3), Reading(e_total_kwh=1000), None)
    assert daily_from_total(db, ts(day, 12), 1012.5) == pytest.approx(12.5)
    assert daily_from_total(db, ts(day, 12), 990) == 0.0
    db.insert(ts(day, 13), Reading(power_kw=2.0, e_total_kwh=1020), None)
    assert integrate_total(db, ts(day, 13) + 600, 4.0) == pytest.approx(1020 + 3.0 * 600 / 3600)
    assert integrate_total(db, ts(day, 13) + 3600, 4.0) == pytest.approx(1020)  # prekid > 15 min


def test_store_reading_computes_missing_energy_and_keeps_extras(tmp_path):
    db = Db(tmp_path / "solar.db")
    t0 = ts(dt.date(2026, 6, 10), 10)
    p = PlantReading(Reading(power_kw=3.0, e_daily_kwh=-1, e_total_kwh=-1), extra={"battery_soc": 55.0})
    store_reading(db, p, t0)
    store_reading(db, PlantReading(Reading(power_kw=3.0, e_daily_kwh=-1, e_total_kwh=-1), extra={"battery_soc": 56.0}), t0 + 300)
    last = db.latest()
    assert last.e_total_kwh == pytest.approx(0.25)
    assert last.e_daily_kwh == pytest.approx(0.0)  # kao C++: početak dana je prvo očitanje s ukupnom > 0
    assert last.extra == {"battery_soc": 56.0}
    store_reading(db, PlantReading(Reading(power_kw=3.0, e_daily_kwh=-1, e_total_kwh=-1)), t0 + 600)
    assert db.latest().e_daily_kwh == pytest.approx(0.25)


def test_days_from_aggregates_prefers_e_daily_and_meter(tmp_path):
    db = Db(tmp_path / "solar.db")
    day = dt.date(2026, 6, 10)
    db.insert(ts(day, 0) + 600, Reading(power_kw=0, e_daily_kwh=99, e_total_kwh=1000), None)  # jučerašnji E-daily prije 01:00
    db.insert(ts(day, 10), Reading(power_kw=5, e_daily_kwh=10, e_total_kwh=1010), 2.0)
    db.insert(ts(day, 14), Reading(power_kw=1, e_daily_kwh=25, e_total_kwh=1025), -3.0)
    days = days_from_aggregates(db.hourly_aggregates(ts(day, 0), ts(day, 24)), day, day)
    assert days[0].kwh == 25
    assert days[0].load == pytest.approx(-1.0)
    assert days[0].exported == pytest.approx(3.0 + 4.0)
    assert days[0].imported == pytest.approx(0.0)


def test_savings_and_dashboard(tmp_path):
    s = config.settings_from_json({"price_kwh": 0.2, "feedin_price_kwh": 0.05})
    assert savings(s, 10, 4) == pytest.approx(6 * 0.2 + 4 * 0.05)
    assert savings(s, 10, 40) == pytest.approx(10 * 0.05)
    db_path = tmp_path / "solar.db"
    with Db(db_path) as db:
        db.insert(ts(dt.date.today(), 0) + 3700, Reading(power_kw=1, e_daily_kwh=1, e_total_kwh=100), None)
    d = DataService(db_path).dashboard(s)
    assert len(d["monthly"]) == 24
    assert d["records"]["first_day"] == dt.date.today().isoformat()
    assert "realtime" in d and "savings" in d


def test_validate_form_rules():
    cur = config.settings_from_json({})
    new, errors = config.validate_form({"modbus_host": "192.168.0.222", "plant_name": "X", "headline": "Y", "currency": "€",
                                        "logger_interface": "", "device_type": "sunspec", "inverter_units": "1, 2,3"}, cur, ["eth0"])
    assert not errors and new["inverter_units"] == "1,2,3" and new["logger_interface"] == ""
    _, errors = config.validate_form({"modbus_host": "999.1.1.1", "plant_name": "", "headline": "Y", "currency": "€",
                                      "night_from": "25:00", "alert_emails": "a@b.hr, nije", "logger_interface": "wlan9"}, cur, ["eth0"])
    assert set(errors) >= {"modbus_host", "plant_name", "night_from", "alert_emails", "logger_interface"}
    _, errors = config.validate_form({"modbus_host": "1.2.3.4", "plant_name": "X", "headline": "Y", "currency": "€",
                                      "device_type": "vendor", "device_profile": "deye_string", "modbus_port": 8899}, cur, [])
    assert "logger_serial" in errors
    new, errors = config.validate_form({"plant_name": "X", "headline": "Y", "currency": "€", "device_type": "vedirect",
                                        "serial_port": "/dev/ttyUSB0, /dev/ttyUSB1"}, cur, [])
    assert not errors and new["serial_port"] == "/dev/ttyUSB0,/dev/ttyUSB1"  # Linux putanje ne idu u velika slova
    assert config.parse_units("1,1") is None and config.parse_units("248") is None


def test_smtp_password_not_carried_to_other_server():
    cur = config.settings_from_json({"smtp_host": "mail.a.hr", "smtp_user": "u", "smtp_password_enc": "tajna", "mail_provider": "smtp"})
    form = {"plant_name": "X", "headline": "Y", "currency": "€", "modbus_host": "1.2.3.4", "smtp_host": "mail.b.hr", "smtp_user": "u",
            "mail_provider": "smtp"}
    new, errors = config.validate_form(form, cur, [])
    assert not errors and new["smtp_password_enc"] == ""


def test_alerts_offline_fault_low_and_daily_limit():
    s = config.settings_from_json({"device_type": "inverter", "alert_offline_min": 30, "peak_power_kwp": 10})
    t = ts(dt.date(2026, 6, 10), 15)
    st, msgs = evaluate_alerts(s, AlertState(), Observation(t, False, t - 31 * 60, error="timeout"))
    assert st.offline_sent and len(msgs) == 1 and "timeout" in msgs[0].body
    st, msgs = evaluate_alerts(s, st, Observation(t + 60, True, t + 60, status=0x0300))
    assert not st.offline_sent and st.fault_sent and len(msgs) == 2
    st, msgs = evaluate_alerts(s, st, Observation(t + 120, True, t + 120, status=0, day_kwh=5, expected_kwh=20))
    assert any("niska" in m.subject for m in msgs) and st.low_day == "2026-06-10"
    full = AlertState(sent_day="2026-06-10", sent_count=20)
    _, msgs = evaluate_alerts(s, full, Observation(t, False, t - 3600))
    assert msgs == []
    hourly = [["2026-06-10T10:00", 1000.0], ["2026-06-10T11:00", 500.0]]
    assert expected_until(hourly, ts(dt.date(2026, 6, 10), 10) + 1800, 10) == pytest.approx(8 + 0.5 * 4)


def test_smartlogger_parse_zip_and_import(tmp_path):
    days = parse_perfmg_day(sample_emap())
    assert days == {dt.date(2024, 6, 1): pytest.approx(599.29), dt.date(2024, 6, 2): 410.0, dt.date(2024, 6, 5): 0.0,
                    dt.date(2024, 6, 6): pytest.approx(123.45)}
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("perf/perfmg_day.emap", sample_emap())
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as z:
        z.writestr("device1.zip", inner.getvalue())
    assert read_perfmg_day("log.zip", outer.getvalue()) == sample_emap()
    with pytest.raises(RuntimeError):
        parse_perfmg_day(b"kratko")
    db = Db(tmp_path / "solar.db")
    db.insert(ts(dt.date(2024, 6, 2), 15), Reading(power_kw=5, e_daily_kwh=300, e_total_kwh=1000), None)
    days[dt.date(2024, 6, 7)] = 77
    res = import_perfmg_days(db, days, dt.date(2024, 6, 7))
    assert (res.imported, res.skipped, res.first, res.last) == (3, 1, dt.date(2024, 6, 1), dt.date(2024, 6, 6))
    out = days_from_aggregates(db.hourly_aggregates(ts(dt.date(2024, 6, 1), 0), ts(dt.date(2024, 6, 8), 0)),
                               dt.date(2024, 6, 1), dt.date(2024, 6, 7))
    assert [round(x.kwh, 2) for x in out] == [599.29, 300.0, 0, 0, 0, 123.45, 0]
    assert import_perfmg_days(db, days, dt.date(2024, 6, 7)).imported == 0
    assert db.latest().e_total_kwh == pytest.approx(1000.0)


def test_report_and_csv(tmp_path):
    db_path = tmp_path / "solar.db"
    with Db(db_path) as db:
        for day in range(1, 4):
            db.insert(ts(dt.date(2025, 3, day), 14), Reading(power_kw=4, e_daily_kwh=10 * day, e_total_kwh=100 * day), None)
    s = config.settings_from_json({"price_kwh": 0.2})
    r = build_report(DataService(db_path), s, 2025, 3)
    assert r["totals"]["kwh"] == pytest.approx(60) and r["best_day"]["date"] == "2025-03-03" and r["complete"]
    assert r["peak"]["kw"] == 4
    csv = report_csv(r).decode("utf-8-sig")
    assert csv.splitlines()[1].startswith("01.03.2025.;10,00;")
    with pytest.raises(RuntimeError):
        build_report(DataService(db_path), s, 2100, 1)
