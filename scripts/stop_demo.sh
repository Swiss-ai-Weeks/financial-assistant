#!/usr/bin/env bash

set -u

ROOT="/home/nvidia/prototype/financial-assistant"


stop_process() {
  name="$1"
  pid_file="$2"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name: no PID file"
    return
  fi

  pid="$(cat "$pid_file")"

  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $name ($pid)..."
    kill "$pid"
  else
    echo "$name: process no longer running"
  fi

  rm -f "$pid_file"
}


stop_process \
  "frontend" \
  "$ROOT/.run/frontend.pid"

stop_process \
  "anomaly API" \
  "$ROOT/.run/anomaly_api.pid"
