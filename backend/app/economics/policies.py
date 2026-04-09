from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict


@dataclass(frozen=True)
class EconomicPolicy:
    policy_id: str
    artist_share: float
    weight_decay_lambda: float
    min_listen_seconds: float
    full_play_threshold_ratio: float
    daily_cap: int
    repeat_window_hours: int
    description: str = ""
    created_at: str = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


POLICIES: Dict[str, EconomicPolicy] = {
    # Baseline policy matching reconstructed V1 semantics.
    "v1": EconomicPolicy(
        policy_id="v1",
        artist_share=0.70,
        weight_decay_lambda=0.22,
        min_listen_seconds=30.0,
        full_play_threshold_ratio=0.3,
        daily_cap=5,
        repeat_window_hours=24,
        description="V1 baseline economics reconstructed into V2 snapshot engine.",
    ),
    # Mild experiment: slightly stronger anti-repeat decay.
    "v2_test_A": EconomicPolicy(
        policy_id="v2_test_A",
        artist_share=0.70,
        weight_decay_lambda=0.26,
        min_listen_seconds=30.0,
        full_play_threshold_ratio=0.3,
        daily_cap=5,
        repeat_window_hours=24,
        description="Experiment A: stronger repeat decay.",
    ),
    # Mild experiment: slightly larger artist share and softer decay.
    "v2_test_B": EconomicPolicy(
        policy_id="v2_test_B",
        artist_share=0.72,
        weight_decay_lambda=0.20,
        min_listen_seconds=30.0,
        full_play_threshold_ratio=0.3,
        daily_cap=5,
        repeat_window_hours=24,
        description="Experiment B: higher artist share and softer repeat decay.",
    ),
}


def get_policy(policy_id: str) -> EconomicPolicy:
    policy = POLICIES.get(str(policy_id))
    if policy is None:
        known = ", ".join(sorted(POLICIES.keys()))
        raise RuntimeError(f"Unknown policy_id={policy_id!r}. Known: {known}")
    return policy
