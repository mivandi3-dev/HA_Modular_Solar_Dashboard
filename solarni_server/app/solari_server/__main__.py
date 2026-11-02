"""Pokretanje: python -m solari_server  (u add-onu: run.sh; samostalno: docker compose ili izravno)

Okolina:
  SOLARI_DATA_DIR    mapa podataka (zadano /data)
  SOLARI_ASSETS_DIR  izvorne slike (zadano app/assets)
  SOLARI_PORT        port API-ja (zadano 8700)
  SOLARI_TOKEN_FILE  kamo zapisati pristupni ključ za dashboard (zadano /share/solarni/api_token; "" = nigdje)
  SOLARI_API_TOKEN   vlastiti ključ (inače se izradi i čuva u <data>/api_token)
  SOLARI_PUBLISH_SENSORS  1/0 – senzori u Home Assistant (MQTT discovery ako je MQTT dostupan, inače REST stanja)
  SOLARI_MQTT_HOST/PORT/USER/PASSWORD  broker (add-on ih dobiva od Mosquitto add-ona preko services: mqtt)
  SOLARI_HA_NOTIFY   "persistent_notification" ili "notify.<usluga>" – obavijesti i u Home Assistant ("" = isključeno)
  SOLARI_COMPACT_AFTER_DAYS  povijest stariju od N dana sažmi na 5-minutne prosjeke (0 = nikad)
  SOLARI_HA_URL / SOLARI_HA_TOKEN  samostalno: adresa HA i dugotrajni ključ (entiteti, senzori, obavijesti)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from aiohttp import web

from . import VERSION
from .api import create_app
from .core import Core


def main() -> None:
    logging.basicConfig(level=os.environ.get("SOLARI_LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    here = Path(__file__).resolve().parent.parent
    token_file = os.environ.get("SOLARI_TOKEN_FILE", "/share/solarni/api_token")
    core = Core(Path(os.environ.get("SOLARI_DATA_DIR", "/data")), Path(os.environ.get("SOLARI_ASSETS_DIR", str(here / "assets"))),
                Path(token_file) if token_file else None, os.environ.get("SOLARI_API_TOKEN", ""),
                os.environ.get("SOLARI_PUBLISH_SENSORS", "1") == "1", os.environ.get("SOLARI_HA_NOTIFY", ""),
                int(os.environ.get("SOLARI_COMPACT_AFTER_DAYS", "0") or 0),
                {"host": os.environ.get("SOLARI_MQTT_HOST", ""), "port": os.environ.get("SOLARI_MQTT_PORT", "1883"),
                 "user": os.environ.get("SOLARI_MQTT_USER", ""), "password": os.environ.get("SOLARI_MQTT_PASSWORD", "")})
    port = int(os.environ.get("SOLARI_PORT", "8700"))
    logging.getLogger("solari").info("Solarni poslužitelj %s – API na portu %d", VERSION, port)
    web.run_app(create_app(core), host=os.environ.get("SOLARI_HOST", "0.0.0.0"), port=port, access_log=None, print=None)


if __name__ == "__main__":
    main()
