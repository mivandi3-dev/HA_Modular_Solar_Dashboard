#!/usr/bin/with-contenv bashio
# Solarni poslužitelj (Home Assistant add-on): opcije → okolina → python -m solari_server
export SOLARI_DATA_DIR=/data
export SOLARI_TOKEN_FILE=/share/solarni/api_token
export SOLARI_API_TOKEN="$(bashio::config 'api_token')"
export SOLARI_PORT="$(bashio::addon.port 8700)"
[ -z "${SOLARI_PORT}" ] || [ "${SOLARI_PORT}" = "null" ] && export SOLARI_PORT=8700
export SOLARI_HA_NOTIFY="$(bashio::config 'ha_notify')"
[ "${SOLARI_HA_NOTIFY}" = "null" ] && export SOLARI_HA_NOTIFY=""
export SOLARI_COMPACT_AFTER_DAYS="$(bashio::config 'compact_after_days')"
if bashio::services.available "mqtt"; then
  export SOLARI_MQTT_HOST="$(bashio::services mqtt 'host')"
  export SOLARI_MQTT_PORT="$(bashio::services mqtt 'port')"
  export SOLARI_MQTT_USER="$(bashio::services mqtt 'username')"
  export SOLARI_MQTT_PASSWORD="$(bashio::services mqtt 'password')"
  bashio::log.info "MQTT: ${SOLARI_MQTT_HOST}:${SOLARI_MQTT_PORT} – elektrana kao uređaj u Home Assistantu"
fi
export SOLARI_PUBLISH_SENSORS="$(bashio::config 'publish_sensors' | sed 's/true/1/;s/false/0/')"
export SOLARI_LOG_LEVEL="$(bashio::config 'log_level')"
mkdir -p /share/solarni
bashio::log.info "Solarni poslužitelj – API na portu ${SOLARI_PORT}"
exec python3 -m solari_server
