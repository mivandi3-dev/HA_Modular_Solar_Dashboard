"""Pokretanje dashboarda: python -m solari_dashboard

Okolina:
  SOLARI_SERVER_URL   adresa Solarnog poslužitelja (zadano http://172.30.32.1:8700 – poslužitelj add-on na istom HA)
  SOLARI_API_TOKEN    pristupni ključ (prazno = čita se iz SOLARI_TOKEN_FILE)
  SOLARI_TOKEN_FILE   zadano /share/solarni/api_token (zapisuje ga poslužitelj)
  SOLARI_DATA_DIR     /data (raspored widgeta, postavke prikaza, PIN)
  SOLARI_PORT         Ingress port (zadano 8099)
  SOLARI_INGRESS_ONLY 1 = promet samo sa Supervisor Ingressa (172.30.32.2)
  SOLARI_VIEW_PORT    port pregleda iz mreže (0 = isključeno)
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from aiohttp import web

from . import VERSION
from .app import Dashboard, create_ingress_app, create_view_app


async def run() -> None:
    here = Path(__file__).resolve().parent.parent
    token_file = os.environ.get("SOLARI_TOKEN_FILE", "/share/solarni/api_token")
    d = Dashboard(Path(os.environ.get("SOLARI_DATA_DIR", "/data")), Path(os.environ.get("SOLARI_WEB_DIR", str(here / "web"))),
                  os.environ.get("SOLARI_SERVER_URL", "http://172.30.32.1:8700"), os.environ.get("SOLARI_API_TOKEN", ""),
                  Path(token_file) if token_file else None)
    log = logging.getLogger("solari.dashboard")
    port = int(os.environ.get("SOLARI_PORT", "8099"))
    ingress = web.AppRunner(create_ingress_app(d, os.environ.get("SOLARI_INGRESS_ONLY", "0") == "1"), access_log=None)
    await ingress.setup()
    await web.TCPSite(ingress, "0.0.0.0", port).start()
    log.info("Solarni monitor (dashboard) %s – Ingress na portu %d, poslužitelj %s", VERSION, port, d.server_url)
    view_port = int(os.environ.get("SOLARI_VIEW_PORT", "0") or 0)
    if view_port:
        view = web.AppRunner(create_view_app(d), access_log=None)
        await view.setup()
        await web.TCPSite(view, "0.0.0.0", view_port).start()
        log.info("Pregled iz mreže na portu %d (uključuje se u Postavke → Sustav, uz pristupni ključ)", view_port)
    await asyncio.Event().wait()


def main() -> None:
    logging.basicConfig(level=os.environ.get("SOLARI_LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
