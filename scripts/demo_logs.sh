#!/usr/bin/env bash
source "$(dirname -- "$0")/demo_common.sh"
case "${1:-}" in
  backend|frontend) exec tail -n 100 -F "$RUNTIME/logs/$1.log" ;;
  *) echo 'Usage: ./scripts/demo_logs.sh backend|frontend'; exit 1 ;;
esac
