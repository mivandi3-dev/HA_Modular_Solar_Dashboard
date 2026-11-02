#!/usr/bin/with-contenv bashio
# Solarni monitor (dashboard, Ingress): opcije → okolina → python -m solari_dashboard
export SOLARI_DATA_DIR=/data
export SOLARI_TOKEN_FILE=/share/solarni/api_token
export SOLARI_SERVER_URL="$(bashio::config 'server_url')"
export SOLARI_API_TOKEN="$(bashio::config 'api_token')"
export SOLARI_LOG_LEVEL="$(bashio::config 'log_level')"
export SOLARI_PORT=8099
export SOLARI_INGRESS_ONLY=1
export SOLARI_VIEW_PORT=8600
export SOLARI_VIEW_PORT_PUBLIC="$(bashio::addon.port 8600)"
[ "${SOLARI_VIEW_PORT_PUBLIC}" = "null" ] && export SOLARI_VIEW_PORT_PUBLIC=""
bashio::log.info "Solarni monitor – poslužitelj ${SOLARI_SERVER_URL}"
exec python3 -m solari_dashboard
