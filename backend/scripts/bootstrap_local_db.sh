#!/usr/bin/env bash
# Fresh SQLite dev DB + Alembic + discovery seed. Run from repo root or backend/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d ".venv" ]]; then
  echo "No .venv found. Create one with:"
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
PY=".venv/bin/python"
PIP=".venv/bin/pip"
ALEMBIC=".venv/bin/alembic"

echo "==> Installing dependencies ($PIP install -r requirements.txt)"
"$PIP" install -r requirements.txt

echo "==> Removing existing SQLite DB (if any)"
rm -f test.db

echo "==> Alembic upgrade head"
"$ALEMBIC" upgrade head

echo "==> Discovery realistic seed"
"$PY" -m app.seeding.seed_discovery_realistic_v2

echo "Done. SQLite file: $ROOT/test.db"
