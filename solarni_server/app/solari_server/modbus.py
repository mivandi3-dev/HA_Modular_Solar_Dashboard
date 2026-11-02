"""Modbus klijent (modbus.cpp): Modbus TCP (MBAP), Solarman V5 (Deye/Sunsynk Wi-Fi logger, TCP 8899) i GoodWe
(Modbus RTU preko UDP-a, port 8899). Huawei SmartLogger 3000 i SUN2000 tablice registara."""
from __future__ import annotations

import socket
import struct
from dataclasses import dataclass

from .i18n import tr
from .storage import Reading


class ModbusError(RuntimeError):
    pass


@dataclass(frozen=True)
class Register:
    address: int
    dtype: str  # U16 | I16 | U32 | I32
    gain: float


POWER_KW = Register(40525, "I32", 1000)
E_DAILY_KWH = Register(40562, "U32", 10)
E_TOTAL_KWH = Register(40560, "U32", 10)
POWER_FACTOR = Register(40532, "I16", 1000)
STATUS = Register(40543, "U16", 1)
METER_POWER_KW = Register(32278, "I32", 1000)  # mjerač na COM portu loggera (vlastiti unit ID)
INV_POWER_KW = Register(32080, "I32", 1000)
INV_E_DAILY_KWH = Register(32114, "U32", 100)
INV_E_TOTAL_KWH = Register(32106, "U32", 100)
INV_POWER_FACTOR = Register(32084, "I16", 1000)
INV_STATUS = Register(32089, "U16", 1)
INV_METER_POWER_KW = Register(37113, "I32", 1000)  # DTSU666-H: > 0 predaja u mrežu


def decode(words: list[int], dtype: str) -> int:
    value = 0
    for w in words:
        value = (value << 16) | w
    bits = 16 * len(words)
    if dtype[0] == "I" and (value >> (bits - 1)) & 1:
        return value - (1 << bits)
    return value


def modbus_crc(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def rtu_read_request(unit: int, fc: int, address: int, count: int) -> bytes:
    f = bytes([unit & 0xFF, fc, address >> 8 & 0xFF, address & 0xFF, count >> 8 & 0xFF, count & 0xFF])
    crc = modbus_crc(f)
    return f + bytes([crc & 0xFF, crc >> 8])


def parse_rtu_response(d: bytes, fc: int, count: int) -> list[int]:
    if len(d) >= 5 and d[1] == (fc | 0x80):
        raise ModbusError(tr("Uređaj je vratio Modbus grešku {code}.", {"code": d[2]}))
    want = 3 + count * 2 + 2
    if len(d) < want or d[1] != fc or d[2] != count * 2:
        raise ModbusError(tr("Neočekivan odgovor uređaja."))
    crc = d[want - 2] | (d[want - 1] << 8)
    if modbus_crc(d[: want - 2]) != crc:
        raise ModbusError(tr("Neispravan kontrolni zbroj u odgovoru uređaja."))
    return [(d[3 + 2 * i] << 8) | d[4 + 2 * i] for i in range(count)]


def solarman_request(serial: int, sequence: int, rtu: bytes) -> bytes:
    length = 15 + len(rtu)
    f = bytearray([0xA5, length & 0xFF, length >> 8, 0x10, 0x45, sequence & 0xFF, 0x00])
    f += struct.pack("<I", serial)
    f += bytes([0x02, 0x00, 0x00]) + bytes(12)  # vrsta okvira, senzor, 3 × vrijeme
    f += rtu
    f.append(sum(f[1:]) & 0xFF)
    f.append(0x15)
    return bytes(f)


def solarman_rtu(f: bytes, serial: int) -> bytes:
    if len(f) < 29 or f[0] != 0xA5 or f[-1] != 0x15:
        raise ModbusError(tr("Neočekivan odgovor uređaja."))
    if sum(f[1:-2]) & 0xFF != f[-2]:
        raise ModbusError(tr("Neispravan kontrolni zbroj u odgovoru uređaja."))
    if struct.unpack_from("<I", f, 7)[0] != serial:
        raise ModbusError(tr("Odgovor je s drugog loggera – provjerite serijski broj loggera."))
    if f[4] != 0x15:
        raise ModbusError(tr("Neočekivan odgovor uređaja."))
    return f[25:-2]


class ModbusClient:
    def __init__(self, host: str, port: int, unit_id: int, source_ip: str = "", timeout_ms: int = 5000,
                 device: str = "SmartLogger", framing: str = "tcp", logger_serial: int = 0) -> None:
        self.host, self.port, self.unit_id = host, port, unit_id
        self.source_ip, self.timeout = source_ip, timeout_ms / 1000
        self.device, self.framing, self.logger_serial = device, framing, logger_serial
        self.sock: socket.socket | None = None
        self.transaction = 0

    def _where(self) -> dict[str, object]:
        return {"device": self.device, "host": self.host, "port": self.port}

    def connect(self) -> None:
        udp = self.framing == "goodwe"
        try:
            infos = socket.getaddrinfo(self.host, self.port, socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)
        except OSError as e:
            raise ModbusError(tr("{device} {host}:{port} – adresa nije ispravna.", self._where())) from e
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)
        self.sock = sock
        if self.source_ip:
            try:
                sock.bind((self.source_ip, 0))  # promet ide kroz karticu s tom adresom
            except OSError as e:
                raise ModbusError(tr("Mrežna kartica s adresom {ip} nije dostupna.", {"ip": self.source_ip})) from e
        sock.settimeout(self.timeout)
        if udp:
            sock.connect(infos[0][4])
            return
        try:
            sock.connect(infos[0][4])
        except OSError as e:
            raise ModbusError(tr("{device} {host}:{port} nije dostupan (provjerite mrežu i je li Modbus TCP uključen).",
                                 self._where())) from e

    def close(self) -> None:
        if self.sock:
            self.sock.close()
            self.sock = None

    def __enter__(self) -> "ModbusClient":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _recv_all(self, n: int) -> bytes:
        assert self.sock
        out = b""
        while len(out) < n:
            try:
                chunk = self.sock.recv(n - len(out))
            except ConnectionResetError:
                chunk = b""
            except OSError as e:
                raise ModbusError(tr("{device} {host} ne odgovara (isteklo vrijeme).", self._where())) from e
            if not chunk:
                # logger prihvati vezu pa je odmah prekine kad IP klijenta nije na popisu dopuštenih
                raise ModbusError(tr("{device} {host}:{port} je prekinuo vezu – IP ovog računala vjerojatno nije na popisu "
                                     "dopuštenih (Modbus TCP → Enable (Limited)).", self._where()))
            out += chunk
        return out

    def _send(self, data: bytes) -> None:
        assert self.sock
        try:
            self.sock.sendall(data)
        except OSError as e:
            raise ModbusError(tr("Slanje prema uređaju nije uspjelo.")) from e

    def read_registers(self, address: int, count: int, unit_id: int, fc: int = 3) -> list[int]:
        if self.framing == "solarman":
            return self._read_solarman(address, count, unit_id, fc)
        if self.framing == "goodwe":
            return self._read_goodwe(address, count, unit_id, fc)
        return self._read_tcp(address, count, unit_id, fc)

    def _read_tcp(self, address: int, count: int, unit_id: int, fc: int) -> list[int]:
        self.transaction = (self.transaction + 1) & 0xFFFF
        self._send(struct.pack(">HHHBBHH", self.transaction, 0, 6, unit_id & 0xFF, fc, address, count))
        head = self._recv_all(9)  # MBAP (7) + funkcija + broj bajtova / kod greške
        if head[7] & 0x80:
            raise ModbusError(tr("{device} je za registar {reg} vratio grešku: {error}",
                                 {"device": self.device, "reg": address, "error": f"kod {head[8]}"}))
        if head[8] != count * 2:
            raise ModbusError(tr("Neočekivan odgovor uređaja."))
        payload = self._recv_all(head[8])
        return list(struct.unpack(f">{count}H", payload))

    def _read_solarman(self, address: int, count: int, unit_id: int, fc: int) -> list[int]:
        self.transaction = (self.transaction + 1) & 0xFF
        seq = self.transaction
        self._send(solarman_request(self.logger_serial, seq, rtu_read_request(unit_id, fc, address, count)))
        for _ in range(5):  # logger šalje i svoje okvire (otkucaji) – preskače se sve osim odgovora
            try:
                head = self._recv_all(3)
            except ModbusError as e:
                raise ModbusError(f"{e} {tr('Provjerite i serijski broj loggera.')}") from e
            length = head[1] | (head[2] << 8)
            frame = head + self._recv_all(10 + length)
            if frame[4] != 0x15 or frame[5] != seq:
                continue
            return parse_rtu_response(solarman_rtu(frame, self.logger_serial), fc, count)
        raise ModbusError(tr("Neočekivan odgovor uređaja."))

    def _read_goodwe(self, address: int, count: int, unit_id: int, fc: int) -> list[int]:
        assert self.sock
        request = rtu_read_request(unit_id, fc, address, count)
        for _ in range(3):  # UDP: zahtjev ili odgovor se mogu izgubiti
            self.sock.send(request)
            try:
                buf = self.sock.recv(600)
            except OSError:
                continue
            if len(buf) < 7 or buf[0] != 0xAA or buf[1] != 0x55:
                raise ModbusError(tr("Neočekivan odgovor uređaja."))
            return parse_rtu_response(buf[2:], fc, count)
        raise ModbusError(tr("{device} {host} ne odgovara (isteklo vrijeme).", self._where()))

    def read_value(self, reg: Register, unit_id: int = -1) -> float:
        words = self.read_registers(reg.address, 2 if reg.dtype[1] == "3" else 1, self.unit_id if unit_id < 0 else unit_id)
        return decode(words, reg.dtype) / reg.gain

    def read_inverter(self, unit_id: int) -> Reading:
        return Reading(self.read_value(INV_POWER_KW, unit_id), self.read_value(INV_E_DAILY_KWH, unit_id),
                       self.read_value(INV_E_TOTAL_KWH, unit_id), self.read_value(INV_POWER_FACTOR, unit_id),
                       int(self.read_value(INV_STATUS, unit_id)))

    def read(self) -> Reading:
        return Reading(self.read_value(POWER_KW), self.read_value(E_DAILY_KWH), self.read_value(E_TOTAL_KWH),
                       self.read_value(POWER_FACTOR), int(self.read_value(STATUS)))

    def read_meter_kw(self, unit_id: int) -> float:
        return self.read_value(METER_POWER_KW, unit_id)
