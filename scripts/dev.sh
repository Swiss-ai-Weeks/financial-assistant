#!/usr/bin/env bash
#
# Run the API and the UI together; Ctrl-C stops both.

set -euo pipefail

cd "$(dirname "$0")/.."

API_PORT="${API_PORT:-8080}"

if [[ ! -x .venv/bin/uvicorn || ! -d frontend/node_modules ]]; then
  echo "Dependencies are missing. Run: make setup" >&2
  exit 1
fi

trap 'kill 0' EXIT

.venv/bin/uvicorn financial_assistant.api.main:app --reload --port "$API_PORT" &

(cd frontend && VITE_API_PROXY="http://127.0.0.1:${API_PORT}" npm run dev) &

echo
echo "  UI   http://localhost:5173"
echo "  API  http://localhost:${API_PORT}/docs"
echo

wait
