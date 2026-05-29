#!/bin/sh

BASE_PATH="${SUPERVISOR_INGRESS_PATH:-}"
HA_TOKEN="${HA_TOKEN:-$SUPERVISOR_TOKEN}"
HA_URL="${HA_URL:-http://supervisor/core}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-true}"

export BASE_PATH HA_TOKEN HA_URL HOST PORT RELOAD

mkdir -p data/dashboards
exec python3 -m uvicorn app.main:app --host="$HOST" --port="$PORT" --reload
