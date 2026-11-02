"""Mrežne kartice i HTTP s izborom kartice (net.cpp) za Linux.

U Home Assistantu poslužitelj radi s host_network: true, pa vidi stvarne kartice računala (eth0, wlan0, end0…).
Odabrana kartica = izvorna adresa (bind) za Modbus, Fronius i internet (prognoza, e-pošta)."""
from __future__ import annotations

import http.client
import ipaddress
import json
import shutil
import socket
import ssl
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

_SKIP = ("lo", "docker", "veth", "hassio", "br-")


def list_interfaces() -> list[dict[str, Any]]:
    """[{name, ipv4, prefix, is_up, link_local_only, speed_mbps}] – isti oblik kao Windows verzija (settings.js)."""
    out: list[dict[str, Any]] = []
    ip = shutil.which("ip")
    if not ip:
        return out
    try:
        raw = subprocess.run([ip, "-j", "addr", "show"], capture_output=True, text=True, timeout=5, check=True).stdout
        items = json.loads(raw)
    except (OSError, subprocess.SubprocessError, ValueError):
        return out
    for it in items:
        name = it.get("ifname", "")
        if not name or name.startswith(_SKIP):
            continue
        addrs = [a for a in it.get("addr_info", []) if a.get("family") == "inet"]
        ipv4 = addrs[0]["local"] if addrs else ""
        prefix = addrs[0].get("prefixlen", 0) if addrs else 0
        speed = 0
        try:
            speed = max(0, int(Path(f"/sys/class/net/{name}/speed").read_text().strip()))
        except (OSError, ValueError):
            pass
        out.append({"name": name, "description": name, "ipv4": ipv4, "prefix": prefix,
                    "is_up": "UP" in it.get("flags", []) or it.get("operstate") == "UP",
                    "link_local_only": bool(ipv4) and ipv4.startswith("169.254."), "speed_mbps": speed})
    return out


def interface_names() -> list[str]:
    return [i["name"] for i in list_interfaces()]


def source_ip(name: str) -> str | None:
    if not name:
        return None
    for i in list_interfaces():
        if i["name"] == name and i["ipv4"]:
            return i["ipv4"]
    return None


def reaches(name: str, host: str) -> bool | None:
    """Je li host u mreži kartice (None = ne zna se, npr. naziv umjesto IP adrese)."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return None
    for i in list_interfaces():
        if i["name"] == name and i["ipv4"]:
            return addr in ipaddress.ip_network(f"{i['ipv4']}/{i['prefix']}", strict=False)
    return None


def default_route_interface() -> str | None:
    try:
        raw = subprocess.run(["ip", "-j", "route", "show", "default"], capture_output=True, text=True, timeout=5).stdout
        routes = json.loads(raw or "[]")
        return routes[0].get("dev") if routes else None
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def http_request(url: str, timeout: float, source: str | None = None, method: str = "GET", body: bytes | None = None,
                 headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    """HTTP(S) zahtjev; source = izvorna IP adresa (kartica). Vraća (status, tijelo)."""
    u = urllib.parse.urlsplit(url)
    src = (source, 0) if source else None
    path = u.path + ("?" + u.query if u.query else "")
    if u.scheme == "https":
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=timeout,
                                                                       source_address=src, context=ssl.create_default_context())
    else:
        conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout, source_address=src)
    try:
        conn.request(method, path or "/", body=body, headers={"User-Agent": "SolarniPosluzitelj-HA", **(headers or {})})
        resp = conn.getresponse()
        return resp.status, resp.read(8 * 1024 * 1024)
    finally:
        conn.close()


def http_get(url: str, timeout: float, source: str | None = None) -> tuple[int, bytes]:
    return http_request(url, timeout, source)


def lan_urls(port: int) -> list[str]:
    return [f"http://{i['ipv4']}:{port}" for i in list_interfaces() if i["is_up"] and i["ipv4"] and not i["link_local_only"]]


def hostname() -> str:
    return socket.gethostname()
