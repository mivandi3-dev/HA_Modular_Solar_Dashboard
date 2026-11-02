"""Protokoli uređaja – isti testni vektori kao C++ testovi (source/windows/tests/test_main.cpp)."""
import struct

import pytest

from solari_server import fronius, offgrid, sunspec
from solari_server.modbus import (ModbusError, decode, modbus_crc, parse_rtu_response, rtu_read_request, solarman_request,
                                  solarman_rtu)
from solari_server.serialio import SerialError
from solari_server.vendors import find_vendor, read_extras, u16, vendor_ranges, vendor_value, Point


def rtu_answer(unit, fc, words):
    r = bytes([unit, fc, len(words) * 2]) + b"".join(struct.pack(">H", w) for w in words)
    crc = modbus_crc(r)
    return r + bytes([crc & 0xFF, crc >> 8])


def solarman_response(serial, seq, rtu):
    length = 14 + len(rtu)
    f = bytearray([0xA5, length & 0xFF, length >> 8, 0x10, 0x15, seq, 0]) + struct.pack("<I", serial) + bytes([2, 1]) + bytes(12)
    f += rtu
    f.append(sum(f[1:]) & 0xFF)
    f.append(0x15)
    return bytes(f)


def test_modbus_rtu_crc_request_response():
    assert rtu_read_request(1, 3, 0, 10) == bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x0A, 0xC5, 0xCD])
    r = rtu_answer(0xF7, 3, [0x1234, 0xABCD])
    assert parse_rtu_response(r, 3, 2) == [0x1234, 0xABCD]
    bad = bytearray(r)
    bad[3] ^= 1
    with pytest.raises(ModbusError):
        parse_rtu_response(bytes(bad), 3, 2)
    with pytest.raises(ModbusError, match="2"):
        parse_rtu_response(bytes([0x01, 0x84, 0x02, 0x00, 0x00]), 4, 2)


def test_decode_signed():
    assert decode([0xFFFF, 0xFFFE], "I32") == -2
    assert decode([0x8000], "I16") == -32768
    assert decode([0x0001, 0x86A0], "U32") == 100000


def test_solarman_frames():
    sn = 2712345678
    rtu = rtu_read_request(1, 3, 0x56, 2)
    req = solarman_request(sn, 7, rtu)
    assert len(req) == 11 + 15 + len(rtu) + 2
    assert req[0] == 0xA5 and req[3] == 0x10 and req[4] == 0x45 and req[5] == 7
    assert struct.unpack_from("<I", req, 7)[0] == sn
    assert req[26:-2] == rtu
    assert req[-2] == sum(req[1:-2]) & 0xFF and req[-1] == 0x15
    answer = rtu_answer(1, 3, [0x1234, 0x0001])
    assert solarman_rtu(solarman_response(sn, 7, answer), sn) == answer
    with pytest.raises(ModbusError, match="serijski"):
        solarman_rtu(solarman_response(sn + 1, 7, answer), sn)


def test_vendor_values_and_ranges():
    regs = {10: 0x0001, 11: 0x86A0, 20: 0xFFFF, 21: 0xFFFE, 30: 0xFF38, 40: 0x000F, 90: 0x4240}
    assert vendor_value(Point(11, 10, True, False, 0.1), regs) == pytest.approx(10000.0)
    assert vendor_value(Point(20, 21, True, True, 1), regs) == pytest.approx(-65537.0)
    assert vendor_value(Point(30, 0, False, True, 1), regs) == pytest.approx(-200.0)
    assert vendor_value(Point(90, 40, True, False, 1), regs) == pytest.approx(1000000.0)
    with pytest.raises(ModbusError):
        vendor_value(Point(99), regs)
    assert vendor_ranges([5002, 5030, 5031, 5003, 5004, 5215, 5216]) == [(5002, 3), (5030, 2), (5215, 2)]


def test_vendor_extras_battery_from_current_and_without_soc():
    prof = find_vendor("epever")
    regs = {0x311A: 80, 0x331A: 2650, 0x331B: 1000, 0x331C: 0, 0x3111: 3000, 0x310E: 50000, 0x310F: 0}
    x = read_extras(prof, lambda pts: regs)
    assert x["battery_soc"] == 80
    assert x["battery_kw"] == pytest.approx(26.5 * 10 / 1000)
    assert x["ac_load_kw"] == pytest.approx(0.5)
    prof_vic = find_vendor("victron")

    def partial(pts):
        if len(pts) > 1:
            raise ModbusError("x")
        if pts[0] == u16(843):
            raise ModbusError("nema baterije")
        return {pts[0].lo: 100}

    x = read_extras(prof_vic, partial)
    assert "battery_soc" not in x and "battery_kw" not in x  # bez baterije nema ni snage baterije
    assert x["ac_load_kw"] == pytest.approx(0.3)


def _model103(w, w_sf, wh, wh_sf, pf, pf_sf, st):
    d = [0] * 50
    d[12], d[13] = w & 0xFFFF, w_sf & 0xFFFF
    d[20], d[21] = pf & 0xFFFF, pf_sf & 0xFFFF
    d[22], d[23], d[24] = wh >> 16, wh & 0xFFFF, wh_sf & 0xFFFF
    d[36] = st
    return d


def test_sunspec_discover_and_inverter():
    regs = {40000: 0x5375, 40001: 0x6E53}
    common = [0] * 66
    for i, c in enumerate("Fronius".ljust(32)[:32].encode()):
        common[i // 2] |= c << (8 if i % 2 == 0 else 0)
    for i, c in enumerate("Symo 10.0-3-M".ljust(32).encode()):
        common[16 + i // 2] |= c << (8 if i % 2 == 0 else 0)
    at = 40002
    for mid, data in ((1, common), (103, _model103(30000, -1, 12_345_678, 0, -950, -1, 4)), (120, [0] * 26)):
        regs[at], regs[at + 1] = mid, len(data)
        for i, v in enumerate(data):
            regs[at + 2 + i] = v
        at += 2 + len(data)
    regs[at] = 0xFFFF

    def read(a, n):
        if a not in regs:
            raise ModbusError("nema")
        return [regs.get(a + i, 0) for i in range(n)]

    models = sunspec.discover(read)
    assert [m.id for m in models] == [1, 103, 120]
    inv = sunspec.find(models, 101, 113)
    r = sunspec.inverter(inv.id, read(inv.address, inv.length))
    assert r.power_kw == pytest.approx(3.0)
    assert r.e_total_kwh == pytest.approx(12345.678)
    assert r.pf == pytest.approx(-0.95)
    assert r.status == 4 and r.e_daily_kwh < 0
    assert sunspec.common_name(read(models[0].address, 32)) == "Fronius Symo 10.0-3-M"
    assert sunspec.inverter(103, _model103(-12, 0, 1000, 0, 100, 0, 2)).power_kw == 0.0
    m203 = [0] * 105
    m203[16], m203[20] = (-1500) & 0xFFFF, 1
    assert sunspec.meter_w(203, m203) == pytest.approx(-15000.0)


def test_fronius_powerflow():
    symo = {"Head": {"Status": {"Code": 0}}, "Body": {"Data": {
        "Site": {"P_PV": 5234.5, "P_Grid": -1200.0, "E_Day": 18345, "E_Total": 45678900.5},
        "Inverters": {"1": {"P": 5234, "E_Day": 18345, "E_Total": 45678900}}}}}
    a = fronius.parse_powerflow(symo, True)
    assert a.reading.power_kw == pytest.approx(5.2345)
    assert a.reading.e_daily_kwh == pytest.approx(18.345)
    assert a.load_kw == pytest.approx(-1.2)
    gen24 = {"Head": {"Status": {"Code": 0}}, "Body": {"Data": {
        "Site": {"P_PV": None, "P_Grid": 350.0, "E_Day": None, "E_Total": None},
        "Inverters": {"1": {"P": 0, "E_Total": 1000000.0}, "2": {"P": 0, "E_Total": 500000.0}}}}}
    g = fronius.parse_powerflow(gen24, True)
    assert g.reading.e_total_kwh == pytest.approx(1500.0) and g.reading.e_daily_kwh < 0
    with pytest.raises(RuntimeError):
        fronius.parse_powerflow({"Head": {"Status": {"Code": 8, "Reason": "Busy"}}}, False)


def test_voltronic_crc_and_qpigs():
    assert offgrid.voltronic_frame("QPIGS") == b"QPIGS\xB7\xA9\r"
    assert offgrid.voltronic_frame("QMOD") == b"QMOD\x49\xC1\r"
    assert offgrid.voltronic_frame("QPIRI") == b"QPIRI\xF8\x54\r"
    fields = "000.0 00.0 230.0 49.9 0161 0119 003 460 26.50 012 085 0041 0014 103.8 26.45 00000 00110110 00 00 00856 010"
    crc = offgrid.voltronic_crc(("(" + fields).encode())
    raw = ("(" + fields).encode() + bytes([crc >> 8, crc & 0xFF]) + b"\r"
    assert offgrid.voltronic_unwrap(raw) == fields
    bad = bytearray(raw)
    bad[5] = ord("9")
    with pytest.raises(SerialError):
        offgrid.voltronic_unwrap(bytes(bad))
    st = offgrid.parse_qpigs(fields)
    assert st.out_v == 230.0 and st.out_w == 119 and st.battery_v == 26.5 and st.battery_pct == 85 and st.pv_w == 856
    assert offgrid.parse_qpigs(" ".join(fields.split()[:16])).pv_w == pytest.approx(14 * 103.8)
    assert offgrid.parse_qpigs("NAK") is None
    assert [offgrid.nominal_system_voltage(v) for v in (13.2, 26.5, 52.1, 0)] == [12, 24, 48, 0]


def ve_block(fields):
    body = b"".join(b"\r\n" + k.encode() + b"\t" + v.encode() for k, v in fields) + b"\r\nChecksum\t"
    return body + bytes([(256 - sum(body) % 256) % 256])


def test_vedirect_blocks_and_summary():
    mppt = ve_block([("PID", "0xA053"), ("SER#", "HQ1"), ("V", "26150"), ("I", "3200"), ("PPV", "85"), ("H19", "1234"), ("H20", "56")])
    shunt = ve_block([("PID", "0xA389"), ("SER#", "HQ2"), ("V", "26100"), ("I", "-1500"), ("P", "-39"), ("SOC", "845")])
    phoenix = ve_block([("PID", "0xA231"), ("SER#", "HQ3"), ("AC_OUT_V", "23000"), ("AC_OUT_S", "230")])
    corrupt = bytearray(ve_block([("PID", "0xA053"), ("SER#", "HQ9"), ("PPV", "999")]))
    corrupt[10] = ord("X")
    blocks = offgrid.parse_vedirect(b"e\t12" + mppt + b":A0002000148\n" + bytes(corrupt) + shunt + phoenix)
    s = offgrid.summarize_vedirect(blocks)
    assert s.pv_w == 85 and s.today_kwh == pytest.approx(0.56) and s.total_kwh == pytest.approx(12.34)
    assert s.extra["battery_soc"] == pytest.approx(84.5)
    assert s.extra["battery_kw"] == pytest.approx(-0.039)
    assert s.extra["battery_v"] == pytest.approx(26.1)
    assert s.extra["ac_load_kw"] == pytest.approx(0.23)
