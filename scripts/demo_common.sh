#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="$ROOT/.run"
umask 077
mkdir -p "$RUNTIME/logs"

# Check PID identity AND kernel start time: a reused PID is never enough.
owned() {
  local service="$1" stamp actual
  local -a arguments
  [[ -f "$RUNTIME/$service.pid" ]] || return 1
  read -r pid stamp < "$RUNTIME/$service.pid"
  [[ "$pid" =~ ^[0-9]+$ && -r "/proc/$pid/stat" ]] || return 1
  actual="$(awk '{print $22}' "/proc/$pid/stat")"
  [[ "$actual" == "$stamp" ]] || return 1
  mapfile -d '' -t arguments < "/proc/$pid/cmdline"
  if [[ "$service" == backend ]]; then
    [[ "${arguments[1]:-}" == "$ROOT/scripts/anomaly_api.py" || ( "${arguments[1]:-}" == -u && "${arguments[2]:-}" == "$ROOT/scripts/anomaly_api.py" ) ]]
  else
    [[ "${arguments[1]:-}" == "$ROOT/frontend/node_modules/vite/bin/vite.js" ]]
  fi
}

lock_runtime() {
  exec 9>"$RUNTIME/control.lock"
  flock -n 9 || { echo 'Another demo start/stop is running'; exit 1; }
}
