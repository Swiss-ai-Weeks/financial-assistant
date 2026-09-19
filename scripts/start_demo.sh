#!/usr/bin/env bash

set -euo pipefail

ROOT="/home/nvidia/prototype/financial-assistant"

cd "$ROOT"

mkdir -p "$ROOT/.run"
mkdir -p "$ROOT/logs"


echo "=========================================="
echo " ClaimGraph demo startup"
echo "=========================================="
echo


# ---------------------------------------------------------
# 1. Validate the files needed by the current demo.
# ---------------------------------------------------------

required_files=(
  "data/cache/market/global_demo_daily.csv"
  "data/cache/market/demo_pair_fits.json"
  "frontend/public/investigation_live_nvidia.json"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "ERROR: missing $file"
    exit 1
  fi
done

echo "[OK] Required demo data exists."


# ---------------------------------------------------------
# 2. Start anomaly API.
#
# nohup means it survives the SSH terminal disappearing.
# ---------------------------------------------------------

if curl -fsS \
  http://127.0.0.1:8001/api/health \
  >/dev/null 2>&1
then
  echo "[OK] Anomaly API already running."
else
  echo "[START] Anomaly API..."

  nohup \
    "$ROOT/.venv/bin/python3" \
    "$ROOT/scripts/anomaly_api.py" \
    > "$ROOT/logs/anomaly_api.log" \
    2>&1 &

  echo $! \
    > "$ROOT/.run/anomaly_api.pid"

  sleep 2

  if curl -fsS \
    http://127.0.0.1:8001/api/health \
    >/dev/null
  then
    echo "[OK] Anomaly API started."
  else
    echo
    echo "ERROR: anomaly API did not start."
    echo "See:"
    echo "  tail -100 logs/anomaly_api.log"
    exit 1
  fi
fi


# ---------------------------------------------------------
# 3. Ensure frontend dependencies exist.
# ---------------------------------------------------------

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "[INSTALL] Frontend dependencies..."

  (
    cd "$ROOT/frontend"
    npm install
  )
fi


# ---------------------------------------------------------
# 4. Start Vite frontend.
# ---------------------------------------------------------

if curl -fsS \
  http://127.0.0.1:5173 \
  >/dev/null 2>&1
then
  echo "[OK] Frontend already running."
else
  echo "[START] Vite frontend..."

  (
    cd "$ROOT/frontend"

    nohup \
      npm run dev \
      > "$ROOT/logs/frontend.log" \
      2>&1 &

    echo $! \
      > "$ROOT/.run/frontend.pid"
  )

  sleep 2

  if curl -fsS \
    http://127.0.0.1:5173 \
    >/dev/null
  then
    echo "[OK] Frontend started."
  else
    echo
    echo "ERROR: frontend did not start."
    echo "See:"
    echo "  tail -100 logs/frontend.log"
    exit 1
  fi
fi


# ---------------------------------------------------------
# 5. Verify frontend -> API proxy.
# ---------------------------------------------------------

echo
echo "[CHECK] Vite -> anomaly API..."

curl -fsS \
  http://127.0.0.1:5173/api/health

echo
echo
echo "=========================================="
echo " ClaimGraph is running"
echo "=========================================="
echo
echo "Backend:"
echo "  http://127.0.0.1:8001"
echo
echo "Frontend:"
echo "  http://127.0.0.1:5173"
echo
echo "Logs:"
echo "  tail -f logs/anomaly_api.log"
echo "  tail -f logs/frontend.log"
echo
echo "Open the usual NVIDIA Launchpad URL"
echo "for the Vite application."
echo
