# Solarni poslužitelj

Bilježi podatke solarne elektrane i daje ih add-onu **Solarni monitor** (dashboard).

Podržani uređaji: Huawei SmartLogger 3000 i SUN2000, SunSpec Modbus (SMA, Fronius, SolarEdge, Kostal, ABB/FIMER, Delta…),
Fronius Solar API, Sungrow, GoodWe, Deye/Sunsynk (i Solarman Wi-Fi logger), Solis, Fox ESS, Growatt, Victron GX te off-grid
sustavi na serijskom portu: Voltronic (Axpert, MPP Solar, EASUN…), Victron VE.Direct, Growatt SPF, EPEver, SRNE.

## Opcije
- **api_token** – prazno: ključ se izradi sam i zapiše u `/share/solarni/api_token` (dashboard ga čita sam).
- **publish_sensors** – senzori elektrane u Home Assistantu (i za Energy nadzornu ploču).
- **ha_notify** – obavijesti (uređaj ne odgovara, greška invertera, niska proizvodnja) i u Home Assistant:
  `persistent_notification` (obavijest u HA), `notify.mobile_app_<mobitel>` (push na mobitel) ili prazno.
- **compact_after_days** – očitanja starija od toliko dana sažimaju se na 5-minutne prosjeke (dnevni vrh ostaje) –
  manja baza i sigurnosne kopije HA. 0 = nikad.
- **log_level**
- **Port 8700** (Mreža) – API za dashboard. Poslužitelj radi u mreži domaćina (Modbus prema uređajima).

## Elektrana u Home Assistantu
S dodatkom **Mosquitto broker** elektrana je **uređaj** (MQTT discovery) sa senzorima snage, energije danas/mjesec/ukupno,
mreže, baterije, temperature i napona – energija se dodaje u **Energy** nadzornu ploču. Bez Mosquitta isti senzori
(`sensor.solarni_*`) upisuju se preko Home Assistant API-ja.

## Entiteti Home Assistanta kao izvor
Ako Home Assistant već čita inverter (npr. integracija Huawei Solar), u Postavke → Mreža izaberite **Home Assistant entiteti**
i upišite ID-eve senzora – uređaj tada ima samo jednu vezu (SmartLogger dopušta ograničen broj Modbus veza).

Postavke uređaja, elektrane i obavijesti uređuju se u dashboardu (Solarni monitor → ⚙ Postavke).

## Off-grid uređaji na USB/RS485
Kabel se pojavi kao `/dev/ttyUSB0` ili `/dev/serial/by-id/…` (Postavke → Mreža → Serijski port). Voltronic preko
USB kabela: upišite `USB`.

## Huawei SmartLogger
Na SmartLoggeru: Settings → Communication Parameters → Modbus TCP → *Enable (Limited)* i dodajte IP adresu Home
Assistanta na popis dopuštenih.
