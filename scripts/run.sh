#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "[ERROR] .venv가 없습니다. 먼저 의존성을 설치하세요."
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

PROFILE="${1:-virtual}"        # virtual | real
MODE="${2:-trade}"             # trade | scan | report | check

if [[ "$PROFILE" != "virtual" && "$PROFILE" != "real" ]]; then
  echo "[ERROR] profile은 virtual 또는 real 이어야 합니다."
  exit 1
fi

case "$MODE" in
  check)
    exec .venv/bin/python main.py --profile "$PROFILE" --check-config
    ;;
  scan)
    exec .venv/bin/python main.py --profile "$PROFILE" --scan-only
    ;;
  report)
    exec .venv/bin/python main.py --profile "$PROFILE" --report
    ;;
  trade)
    exec .venv/bin/python main.py --profile "$PROFILE"
    ;;
  *)
    echo "[ERROR] mode는 trade|scan|report|check 중 하나여야 합니다."
    exit 1
    ;;
esac
