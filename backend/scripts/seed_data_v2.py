#!/usr/bin/env python3
"""
Deprecated seed entrypoint.

Use ``python scripts/seed.py`` from repository root.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.seeding.seed_system import run_seed_system


def _scale_from_events(events: int) -> str:
    if events <= 700:
        return "small"
    if events <= 1700:
        return "medium"
    return "large"


def main() -> None:
    parser = argparse.ArgumentParser(description="Deprecated: delegates to scripts/seed.py.")
    parser.add_argument("--events", type=int, default=1200, help="Deprecated. Mapped to --scale.")
    parser.add_argument("--no-reset", action="store_true", help="Deprecated. Equivalent to omitting --reset.")
    parser.add_argument("--seed", type=int, default=42, help="Mapped to --rng-seed.")
    parser.add_argument("--policy-id", type=str, default="v1", help="Economics policy id.")
    args = parser.parse_args()

    scale = _scale_from_events(int(args.events))
    summary = run_seed_system(
        reset=not bool(args.no_reset),
        scale=scale,
        rng_seed=int(args.seed),
        policy_id=str(args.policy_id),
    )
    print("[DEPRECATED] backend/scripts/seed_data_v2.py -> scripts/seed.py")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
