#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY_BIN="$ROOT_DIR/.venv/bin/python"

if [ ! -x "$PY_BIN" ]; then
  echo "Python interpreter not found at $PY_BIN"
  exit 1
fi

echo "Using interpreter: $PY_BIN"
"$PY_BIN" -c "import sys; assert sys.version_info[:2] == (3, 9), f'Expected Python 3.9, got {sys.version.split()[0]}'"

export PYTHONPYCACHEPREFIX="$ROOT_DIR/.pycache_guard"
mkdir -p "$PYTHONPYCACHEPREFIX"

echo "Compiling backend sources with Python 3.9..."
"$PY_BIN" -m py_compile \
  "$ROOT_DIR/worker.py" \
  "$ROOT_DIR/app/main.py" \
  "$ROOT_DIR/app/api/routes.py" \
  "$ROOT_DIR/app/services/analytics_service.py"

echo "py39 compatibility guard: OK"
