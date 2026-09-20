#!/usr/bin/env bash
source "$(dirname -- "$0")/demo_common.sh"
lock_runtime
for service in frontend backend; do
  if owned "$service"; then
    kill -TERM "$pid"
    for ((attempt=0; attempt<30; attempt++)); do
      owned "$service" || break
      sleep .2
    done
    if owned "$service"; then
      echo "$service still stopping; PID file retained"
      continue
    fi
    echo "$service stopped"
  else
    echo "$service not running under this checkout (no process killed)"
  fi
  rm -f -- "$RUNTIME/$service.pid"
done
