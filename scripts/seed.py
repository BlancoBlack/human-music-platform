#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
ENV_PATH = BACKEND_ROOT / ".env"


def _load_backend_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_PATH)
        load_dotenv()
        return
    except Exception:
        pass
    if not ENV_PATH.is_file():
        return
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed product-realistic platform demo data.")
    parser.add_argument("--reset", action="store_true", help="Wipe domain tables before seeding.")
    parser.add_argument(
        "--scale",
        type=str,
        default="medium",
        choices=("small", "medium", "large"),
        help="Listening simulation scale.",
    )
    parser.add_argument("--rng-seed", type=int, default=42, help="Deterministic seed for event simulation.")
    parser.add_argument("--policy-id", type=str, default="v1", help="Economics policy id used for snapshots.")
    args = parser.parse_args()

    _load_backend_env()
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    from app.seeding.seed_system import run_seed_system

    summary = run_seed_system(
        reset=bool(args.reset),
        scale=str(args.scale),
        rng_seed=int(args.rng_seed),
        policy_id=str(args.policy_id),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
