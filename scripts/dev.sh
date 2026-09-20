#!/usr/bin/env bash
#
# Run the API and the UI together; Ctrl-C stops both.

set -euo pipefail

cd "$(dirname "$0")/.."

# Shared machines often have 8080 taken (on the hackathon
# GPU box it belongs to the instance's own shell gateway, which
# must not be stopped). Start from the requested port and take
# the first free one, so the API never silently fails to bind
# while the UI comes up and talks to somebody else's server.
port_is_free() {
  ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

API_PORT="${API_PORT:-8080}"
REQUESTED_PORT="$API_PORT"

while ! port_is_free "$API_PORT"; do
  API_PORT=$((API_PORT + 1))
done

if [[ "$API_PORT" != "$REQUESTED_PORT" ]]; then
  echo "Port $REQUESTED_PORT is in use: the API will listen on $API_PORT."
fi

if [[ ! -x .venv/bin/uvicorn || ! -d frontend/node_modules ]]; then
  echo "Dependencies are missing. Run: make setup" >&2
  exit 1
fi

trap 'kill 0' EXIT INT TERM

.venv/bin/uvicorn financial_assistant.api.main:app --reload --port "$API_PORT" &

(cd frontend && VITE_API_PROXY="http://127.0.0.1:${API_PORT}" npm run dev) &

echo
echo "  API  http://localhost:${API_PORT}/docs"
echo "  UI   the address Vite prints below (5173, or the next free port)"
echo

wait
