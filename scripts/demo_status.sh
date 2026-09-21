#!/usr/bin/env bash
source "$(dirname -- "$0")/demo_common.sh"
for service in backend frontend; do
  port=8001
  [[ "$service" == frontend ]] && port=5173
  if owned "$service"; then
    echo "$service RUNNING · PID $pid · port $port"
  else
    echo "$service STOPPED / untracked · port $port"
  fi
done
