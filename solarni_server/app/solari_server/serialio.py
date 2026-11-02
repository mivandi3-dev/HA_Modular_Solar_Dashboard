"""Serijske veze za off-grid uređaje (serial.cpp) na Linuxu: USB-serijski kabel, RS232, RS485 pretvarač (/dev/ttyUSB0,
/dev/serial/by-id/…) i Voltronic preko USB HID-a (/dev/hidraw*, USB 0665:5161)."""
from __future__ import annotations

import glob
import os
import select
import time
from pathlib import Path
from typing import Callable

from .i18n import tr
from .modbus import ModbusError, parse_rtu_response, rtu_read_request


class SerialError(RuntimeError):
    pass


class SerialPort:
    def __init__(self, port: str, baud: int, timeout_ms: int = 2000) -> None:
        try:
            import serial  # pyserial
        except ImportError as e:  # pragma: no cover - paket je u slici
            raise SerialError("pyserial nije instaliran") from e
        self.name = port
        try:
            self.port = serial.Serial(port, baudrate=baud, bytesize=8, parity="N", stopbits=1, timeout=0.05,
                                      write_timeout=timeout_ms / 1000)
        except (serial.SerialException, OSError, ValueError) as e:
            raise SerialError(tr("{port}: nema podataka", {"port": port}) + f" ({e})") from e

    def close(self) -> None:
        self.port.close()

    def __enter__(self) -> "SerialPort":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def write(self, data: bytes) -> None:
        self.port.write(data)
        self.port.flush()

    def purge(self) -> None:
        self.port.reset_input_buffer()

    def read_until(self, timeout_ms: int, done: Callable[[bytes, int], bool] | None, want: int = 0) -> bytes:
        deadline = time.monotonic() + timeout_ms / 1000
        out = b""
        while time.monotonic() < deadline:
            chunk = self.port.read(4096)
            if chunk:
                out += chunk
                if done and done(out, want):
                    break
        return out


def list_serial_ports() -> list[str]:
    """Postojeći portovi: stabilna imena /dev/serial/by-id/* prvo, zatim ttyUSB/ttyACM/ttyAMA/ttyS s uređajem."""
    found: list[str] = sorted(glob.glob("/dev/serial/by-id/*"))
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*", "/dev/ttyS[0-9]"):
        found += sorted(glob.glob(pattern))
    if os.name == "nt":  # razvoj na Windowsu
        try:
            from serial.tools import list_ports

            found += [p.device for p in list_ports.comports()]
        except ImportError:
            pass
    if glob.glob("/dev/hidraw*"):
        found.append("USB")
    return list(dict.fromkeys(found))


def rtu_serial_read(port: SerialPort, unit: int, fc: int, address: int, count: int) -> list[int]:
    req = rtu_read_request(unit, fc, address, count)
    port.purge()
    port.write(req)

    def complete(s: bytes, want: int) -> bool:
        if len(s) >= 2 and s[1] & 0x80:
            return len(s) >= 5
        return len(s) >= want

    resp = port.read_until(2000, complete, 5 + 2 * count)
    if not resp:
        raise ModbusError(tr("Uređaj na serijskom portu ne odgovara – provjerite kabel, brzinu i Modbus adresu."))
    return parse_rtu_response(resp, fc, count)


# ---------------------------------------------------------------- Voltronic USB HID
VOLTRONIC_VID_PID = ("0665", "5161")


def _voltronic_hidraw() -> str | None:
    for dev in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent = Path(dev, "device", "uevent")
        try:
            text = uevent.read_text().upper()
        except OSError:
            continue
        vid, pid = VOLTRONIC_VID_PID
        if f"0000{vid}:0000{pid}".upper() in text or f"{vid}:{pid}".upper() in text:
            return "/dev/" + Path(dev).name
    hid = sorted(glob.glob("/dev/hidraw*"))
    return hid[0] if len(hid) == 1 else None  # jedan HID uređaj – vjerojatno izmjenjivač


def voltronic_hid_query(command: str, timeout_ms: int = 3000) -> str:
    from .offgrid import voltronic_frame, voltronic_unwrap

    path = _voltronic_hidraw()
    if not path:
        raise SerialError(tr("USB uređaji nisu dostupni."))
    frame = voltronic_frame(command)
    fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    try:
        for i in range(0, len(frame), 8):  # HID izvješća po 8 bajtova (bez ID-a izvješća)
            os.write(fd, b"\x00" + frame[i:i + 8].ljust(8, b"\x00"))
        deadline = time.monotonic() + timeout_ms / 1000
        raw = b""
        while time.monotonic() < deadline and b"\r" not in raw:
            r, _, _ = select.select([fd], [], [], 0.2)
            if r:
                raw += os.read(fd, 64).rstrip(b"\x00")
        return voltronic_unwrap(raw)
    finally:
        os.close(fd)
