#!/usr/bin/env bash
set -euo pipefail

APP_MODE="${APP_MODE:-dashboard}"           # dashboard | trader | fullstack
TRADING_PROFILE="${TRADING_PROFILE:-virtual}"
PORT="${PORT:-8501}"

mkdir -p logs reports/daily

run_dashboard() {
  exec streamlit run dashboard/app.py \
    --server.address 0.0.0.0 \
    --server.port "$PORT" \
    --server.headless true
}

run_trader() {
  exec python main.py --profile "$TRADING_PROFILE"
}

if [[ "$APP_MODE" == "dashboard" ]]; then
  run_dashboard
elif [[ "$APP_MODE" == "trader" ]]; then
  python main.py --profile "$TRADING_PROFILE" --check-config
  run_trader
elif [[ "$APP_MODE" == "fullstack" ]]; then
  python main.py --profile "$TRADING_PROFILE" --check-config
  python main.py --profile "$TRADING_PROFILE" &
  trader_pid=$!
  trap 'kill $trader_pid 2>/dev/null || true' EXIT INT TERM
  run_dashboard
else
  echo "[ERROR] APP_MODE must be one of: dashboard | trader | fullstack"
  exit 1
fi
