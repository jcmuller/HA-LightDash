#!/usr/bin/with-contenv bashio

export HA_URL="http://supervisor/core"
export HA_TOKEN="$SUPERVISOR_TOKEN"
export BASE_PATH="${SUPERVISOR_INGRESS_PATH:-}"

mkdir -p /data/dashboards

exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000