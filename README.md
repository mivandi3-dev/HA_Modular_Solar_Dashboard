# ☀️ Solarni monitor for Home Assistant

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black)](https://revolut.me/markog68z)
[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmivandi3-dev%2FHA_Modular_Solar_Dashboard)

**[English](#english) · [Hrvatski](#hrvatski)**

Home Assistant version of [Modular Solar Dashboard](https://github.com/mivandi3-dev/Modular_Solar_Dashboard)
(Windows and Android, [solardashboard.bid](https://solardashboard.bid)).

---

## English

Two add-ons in one repository:

| Add-on | What it does |
|---|---|
| **Solarni poslužitelj** (solar server) | Reads the plant (Modbus TCP, Solarman V5, GoodWe UDP, Fronius HTTP, serial port), records to SQLite, weather forecast, alerts, monthly reports, images, history import. Publishes the plant to Home Assistant (MQTT device or sensors). Can also run **standalone** on any Linux machine (Docker). |
| **Solarni monitor** (dashboard) | Opens from the Home Assistant sidebar (Ingress). The same dashboard as the Windows app: 27 widgets on a 12 × 5 grid, up to 6 rotating pages, drag-and-drop editor, 11 palettes, icon themes, 4 designs, night mode, 10 languages, settings, monthly reports (PDF print, CSV). |

```
 inverter/logger ──Modbus/HTTP/RS485──► Solar server add-on (or a separate Linux machine) ──API + key──► Solarni monitor add-on (Ingress) ──► browser / HA app
                           │                      ▲                                                            └─ optional port 8600: read-only view for a lobby TV
   HA integration entities ┘ (optional source)    └─► MQTT device / sensors (Energy dashboard), notifications in HA
```

**Supported devices:** Huawei SmartLogger 3000 and SUN2000 (incl. LUNA2000 battery), SunSpec Modbus (SMA, Fronius,
SolarEdge, Kostal, ABB/FIMER, Delta…), Fronius Solar API (Datamanager, GEN24), Sungrow, GoodWe, Deye/Sunsynk (also via the
Solarman Wi-Fi logger), Solis, Fox ESS, Growatt, Victron Energy GX, **off-grid** systems on USB/RS232/RS485 (Voltronic/Axpert,
Victron VE.Direct, Growatt SPF, EPEver, SRNE) – and **any entities Home Assistant already reads** (e.g. the Huawei Solar,
SolarEdge, Fronius or Enphase integrations), so the device keeps a single connection.

### Installation
1. Click **Add repository to Home Assistant** above (or *Settings → Add-ons → Add-on store → ⋮ → Repositories* and add
   `https://github.com/mivandi3-dev/HA_Modular_Solar_Dashboard`).
2. Install and start **Solarni poslužitelj**, then **Solarni monitor** (the first install builds the images locally –
   a few minutes on a Raspberry Pi).
3. Open **Solarni monitor** from the sidebar → the wizard (network/device, plant, display) → *Save*.
4. Optional: install the **Mosquitto broker** add-on (and the MQTT integration) – the plant then appears as a device with
   entities you can rename and add to the **Energy** dashboard.

There are no app users: access is your Home Assistant login. The server only accepts requests with its API key, which it
writes to `/share/solarni/api_token` – the dashboard reads it automatically. Settings and the widget layout can also be
locked with a PIN (public screens).

### Add-on options
**Solarni poslužitelj:** `api_token` (empty = generated), `publish_sensors` (MQTT device when Mosquitto is installed,
otherwise sensors via the HA API), `ha_notify` (`persistent_notification`, `notify.mobile_app_<phone>` or empty – alerts
in Home Assistant, in addition to email), `compact_after_days` (readings older than this are reduced to 5-minute averages,
the daily peak is kept; 0 = never), port 8700 (Network). A health check (Docker HEALTHCHECK) restarts the add-on if recording stops.

**Solarni monitor:** `server_url` (`http://172.30.32.1:8700` for the add-on on the same HA, otherwise `http://IP:8700`),
`api_token` (empty on the same HA), port 8600 for the optional read-only network view.

### Server on a separate machine
```
git clone https://github.com/mivandi3-dev/HA_Modular_Solar_Dashboard && cd HA_Modular_Solar_Dashboard/solarni_server
docker compose up -d
docker compose exec solarni-server cat /data/api_token
```
In the **Solarni monitor** options set `server_url: http://<machine IP>:8700` and `api_token: <key>`.

### Moving from Windows
*Settings → System → Import history from file (solar.db)* accepts the Windows server database (same schema). Lifetime
production from a SmartLogger: *Import history from SmartLogger (log.zip)*.

---

## Hrvatski

Dva dodatka (add-ona) u jednom repozitoriju:

| Dodatak | Što radi |
|---|---|
| **Solarni poslužitelj** | čita elektranu (Modbus TCP, Solarman V5, GoodWe UDP, Fronius HTTP, serijski port), bilježi u SQLite, prognoza, obavijesti, mjesečni izvještaji, slike, uvoz povijesti; elektranu objavljuje u Home Assistant (MQTT uređaj ili senzori). Može raditi i **samostalno** na bilo kojem Linux računalu (Docker). |
| **Solarni monitor** (dashboard) | otvara se iz bočne trake Home Assistanta (Ingress). Isti dashboard kao Windows aplikacija: 27 widgeta, 6 stranica, editor rasporeda, palete, teme ikona, 4 izgleda, noćni način, 10 jezika, postavke, izvještaji (PDF ispis, CSV). |

**Podržani uređaji:** Huawei SmartLogger 3000 i SUN2000 (s baterijom LUNA2000), SunSpec Modbus (SMA, Fronius, SolarEdge,
Kostal, ABB/FIMER, Delta…), Fronius Solar API, Sungrow, GoodWe, Deye/Sunsynk (i preko Solarman Wi-Fi loggera), Solis,
Fox ESS, Growatt, Victron Energy GX, **off-grid** sustavi na USB/RS232/RS485 (Voltronic/Axpert, Victron VE.Direct, Growatt SPF,
EPEver, SRNE) – i **entiteti koje Home Assistant već čita** (npr. integracije Huawei Solar, SolarEdge, Fronius, Enphase),
pa uređaj ima samo jednu vezu.

### Instalacija
1. Kliknite **Add repository to Home Assistant** gore (ili *Postavke → Dodaci → Trgovina dodataka → ⋮ → Repozitoriji* i dodajte
   `https://github.com/mivandi3-dev/HA_Modular_Solar_Dashboard`).
2. Instalirajte i pokrenite **Solarni poslužitelj**, zatim **Solarni monitor** (prva instalacija gradi slike lokalno – na
   Raspberry Piju nekoliko minuta).
3. Otvorite **Solarni monitor** u bočnoj traci → čarobnjak (mreža/uređaj, elektrana, prikaz) → *Spremi*.
4. Po želji: dodatak **Mosquitto broker** (i integracija MQTT) – elektrana se tada pojavi kao uređaj s entitetima koje možete
   preimenovati i dodati u **Energy** nadzornu ploču.

Korisnika aplikacije nema: pristup je vaša prijava u Home Assistant. Poslužitelj prima samo zahtjeve s pristupnim ključem,
koji sam zapiše u `/share/solarni/api_token` – dashboard ga čita sam. Postavke i raspored widgeta mogu se dodatno zaključati
PIN-om (javni zasloni).

### Opcije
**Solarni poslužitelj:** `api_token` (prazno = izradi se sam), `publish_sensors` (MQTT uređaj kad je Mosquitto instaliran,
inače senzori preko HA API-ja), `ha_notify` (`persistent_notification`, `notify.mobile_app_<mobitel>` ili prazno – obavijesti
u Home Assistantu, uz e-poštu), `compact_after_days` (starija očitanja sažimaju se na 5-minutne prosjeke, dnevni vrh ostaje;
0 = nikad), port 8700 (Mreža). Provjera zdravlja (Docker HEALTHCHECK) ponovno pokrene dodatak ako bilježenje stane.

**Solarni monitor:** `server_url` (`http://172.30.32.1:8700` za dodatak na istom HA, inače `http://IP:8700`), `api_token`
(prazno na istom HA), port 8600 za izborni pregled iz mreže (samo čitanje).

### Poslužitelj na zasebnom računalu
```
git clone https://github.com/mivandi3-dev/HA_Modular_Solar_Dashboard && cd HA_Modular_Solar_Dashboard/solarni_server
docker compose up -d
docker compose exec solarni-server cat /data/api_token
```
U opcijama dodatka **Solarni monitor**: `server_url: http://<IP računala>:8700`, `api_token: <ključ>`.

### Prijelaz s Windows verzije
*Postavke → Sustav → Uvezi povijest iz datoteke (solar.db)* prima bazu Windows poslužitelja (ista shema). Proizvodnja od
puštanja u rad sa SmartLoggera: *Uvezi povijest sa SmartLoggera (log.zip)*.

### Razlike u odnosu na Windows
Datoteke se biraju i preuzimaju u pregledniku; nema korisnika, 2FA, uparivanja ni Cloudflare tunela (udaljeni pristup ide
preko Home Assistanta); razlučivost, monitor i pokretanje pri prijavi odlučuje uređaj; tajne su u `/data/secrets.json`
(vidi ih samo dodatak); serijski portovi su `/dev/ttyUSB0` ili `/dev/serial/by-id/…`.

---

## Development / Razvoj
```
python -m venv venv && venv/bin/pip install aiohttp pyserial pillow paho-mqtt pytest pytest-asyncio
venv/bin/python -m pytest
```
Server: `cd solarni_server/app && SOLARI_DATA_DIR=./data SOLARI_PORT=18700 python -m solari_server` ·
Dashboard: `cd solarni_dashboard/app && SOLARI_SERVER_URL=http://127.0.0.1:18700 SOLARI_TOKEN_FILE=../../solarni_server/app/data/api_token SOLARI_PORT=18099 python -m solari_dashboard`
→ http://127.0.0.1:18099

## Credits and licences / Zasluge i licence
Header photo: NASA/Troy Cryder (public domain). Font: Plus Jakarta Sans (SIL OFL). Libraries: aiohttp, pyserial, Pillow,
paho-mqtt, plotly.js (MIT), qrcode-generator (MIT). Weather: [Open-Meteo](https://open-meteo.com) (CC BY 4.0).
Free for personal use. All rights to the source code reserved. / Besplatno za osobnu upotrebu; sva prava na izvorni kod pridržana.
