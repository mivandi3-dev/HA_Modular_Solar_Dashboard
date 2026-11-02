"""Vrsta uređaja „Home Assistant entiteti”: snaga, energija, mreža i baterija iz senzora koje Home Assistant već čita
(npr. integracija Huawei Solar, SolarEdge, Fronius, Enphase). Uređaj tada ima samo jednu vezu – onu s HA integracijom –
što je važno kod SmartLoggera i invertera s ograničenim brojem Modbus veza. Jedinice se pretvaraju prema
unit_of_measurement (W/kW/MW, Wh/kWh/MWh)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import ha_api
from .i18n import tr

if TYPE_CHECKING:
    from .devices import PlantReading

POWER = {"w": 0.001, "kw": 1.0, "mw": 1000.0}
ENERGY = {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0}


def value(entity: str, units: dict[str, float] | None) -> float:
    st = ha_api.state(entity)
    raw = st.get("state")
    try:
        v = float(raw)
    except (TypeError, ValueError) as e:
        raise RuntimeError(tr("Entitet {entity} nema vrijednost ({state}).", {"entity": entity, "state": raw})) from e
    if units is None:
        return v
    unit = str((st.get("attributes") or {}).get("unit_of_measurement", "")).strip().lower()
    return v * units.get(unit, 1.0)  # bez jedinice: kW / kWh


def read_homeassistant(s: dict[str, Any]) -> "PlantReading":
    from .devices import PlantReading

    if not s["ha_power_entity"]:
        raise RuntimeError(tr("Upišite ID entiteta, npr. sensor.inverter_active_power."))
    out = PlantReading(device_name="Home Assistant")
    out.reading.power_kw = max(0.0, value(s["ha_power_entity"], POWER))
    out.reading.e_daily_kwh = value(s["ha_today_entity"], ENERGY) if s["ha_today_entity"] else -1
    out.reading.e_total_kwh = value(s["ha_total_entity"], ENERGY) if s["ha_total_entity"] else -1
    out.reading.pf = None
    out.reading.status = 1 if out.reading.power_kw > 0 else 0
    if s["ha_grid_entity"]:
        try:  # greška mjerača ne poništava očitanje elektrane
            grid = value(s["ha_grid_entity"], POWER)
            out.load_kw = -grid if s["meter_invert"] else grid  # load_kw: pozitivno = uzimanje iz mreže
        except RuntimeError as e:
            out.meter_error = str(e)
    if s["ha_battery_soc_entity"]:
        try:
            out.extra["battery_soc"] = value(s["ha_battery_soc_entity"], None)
            if s["ha_battery_power_entity"]:
                out.extra["battery_kw"] = value(s["ha_battery_power_entity"], POWER)
                out.extra["battery_dir"] = True
        except RuntimeError:
            out.extra = {}
    return out
