#!/usr/bin/env bash
source "$(dirname -- "$0")/demo_common.sh"
lock_runtime
cd "$ROOT"
for file in .venv/bin/python scripts/anomaly_api.py frontend/node_modules/vite/bin/vite.js data/cache/market/global_demo_daily.csv data/cache/market/demo_pair_fits.json; do
  [[ -f "$file" ]] || { echo "Missing required file: $file"; exit 1; }
done
# Optional existing server-only shell environment file. Never print its contents.
if [[ -n "${BOOKREADER_ENV_FILE:-}" ]]; then
  [[ -r "$BOOKREADER_ENV_FILE" ]] || { echo 'BOOKREADER_ENV_FILE is unreadable'; exit 1; }
  set -a
  source "$BOOKREADER_ENV_FILE"
  set +a
elif [[ -f "$ROOT/.env.bookreader" ]]; then
  set -a
  source "$ROOT/.env.bookreader"
  set +a
fi
start() {
  local service="$1" port="$2" health="$3"
  shift 3
  if owned "$service"; then
    echo "$service already running (PID $pid, port $port)"
    return
  fi
  # Refuse occupied ports; never adopt an unrelated process.
  if "$ROOT/.venv/bin/python" -c 'import socket,sys; s=socket.socket(); sys.exit(s.connect_ex(("127.0.0.1",int(sys.argv[1]))))' "$port"; then
    echo "Port $port occupied by an untracked service; stop it explicitly first"
    exit 1
  fi
  nohup setsid "$@" </dev/null >"$RUNTIME/logs/$service.log" 2>&1 9>&- &
  local child=$!
  echo "$child $(awk '{print $22}' "/proc/$child/stat")" > "$RUNTIME/$service.pid"
  for ((attempt=0; attempt<30; attempt++)); do
    if owned "$service" && curl -fsS "$health" >/dev/null 2>&1; then
      echo "$service ready (PID $pid, port $port)"
      return
    fi
    sleep 1
  done
  echo "$service did not become ready; inspect ./scripts/demo_logs.sh $service"
  exit 1
}
start backend 8001 http://127.0.0.1:8001/api/health "$ROOT/.venv/bin/python" -u "$ROOT/scripts/anomaly_api.py"
# Frontend needs no corpus credentials; do not pass the server token to Vite.
unset BOOKREADER_API_TOKEN
cd "$ROOT/frontend"
start frontend 5173 http://127.0.0.1:5173 node "$ROOT/frontend/node_modules/vite/bin/vite.js" --strictPort
