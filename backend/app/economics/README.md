# Economics Policy Layer

This folder contains the policy versioning system for the V2 snapshot engine.

The goal is simple:

- one ledger truth
- one policy per snapshot
- deterministic, reproducible economics

## What This Gives You

- Versioned economic configurations (`v1`, experiments, future variants)
- Snapshot-level policy freezing (snapshot is self-describing)
- Safe policy experiments without touching payout allocation logic
- Reproducibility: same input data + same policy => same output

## Core Files

- `policies.py`
  - `EconomicPolicy` dataclass
  - `POLICIES` registry
  - `get_policy(policy_id)` resolver/guardrail
- `__init__.py`
  - package export helpers

## Policy Schema

Each policy defines:

- `policy_id`
- `artist_share`
- `weight_decay_lambda`
- `min_listen_seconds`
- `full_play_threshold_ratio`
- `daily_cap`
- `repeat_window_hours`
- optional metadata: `description`, `created_at`

Even if some fields are not yet fully enforced by runtime validation paths, they are still important for traceability and future evolution.

## How It Works End-to-End

1. A caller runs `build_snapshot(..., policy_id="v1")`.
2. `build_snapshot` loads the policy with `get_policy(policy_id)`.
3. Snapshot inputs are built using policy parameters (currently artist share is applied directly in money base).
4. Policy metadata is frozen into `payout_input_snapshots`:
   - `policy_id`
   - `policy_artist_share`
   - `policy_weight_decay_lambda`
   - `policy_json`
5. Payout generation uses snapshot tables only (no policy drift at payout time).

This means ledger behavior is anchored to the frozen snapshot, not mutable global config.

## Small Tutorial

### 1) Run baseline parity + policy comparison

From `backend/`:

```bash
python scripts/test_v1_vs_v2_parity.py
```

The harness will:

- generate realistic data
- run parity checks (V1 vs V2 baseline policy)
- build additional policy snapshots (`v2_test_A`, `v2_test_B`)
- print per-song and per-artist deltas versus baseline

### 2) Run a quick targeted run

```bash
python scripts/test_v1_vs_v2_parity.py --events 300 --seed 42
```

Use this for quick iteration when tuning policies.

### 3) Add a new policy

In `policies.py`, add a new `EconomicPolicy` entry to `POLICIES`, for example:

```python
"v2_test_C": EconomicPolicy(
    policy_id="v2_test_C",
    artist_share=0.71,
    weight_decay_lambda=0.24,
    min_listen_seconds=30.0,
    full_play_threshold_ratio=0.3,
    daily_cap=5,
    repeat_window_hours=24,
    description="Experiment C",
)
```

Then include it in your harness/comparison flow where desired.

### 4) Build a snapshot with a specific policy

Any caller can set:

```python
build_snapshot(..., policy_id="v2_test_A")
```

If policy ID is unknown, snapshot build fails fast.

## How To Update Safely

When changing economic parameters:

1. Never mutate existing policy IDs in place for production meaning.
2. Add a new policy ID instead (versioned change).
3. Run parity and multi-run harness checks.
4. Review per-song and per-artist deltas.
5. Promote policy only after explicit signoff.

## Important Guardrails

- Do not modify payout line allocation logic for policy experiments.
- Do not apply policy in UI-only transformations.
- Do not allow multiple policies inside one snapshot.
- Keep money allocation integer-only in ledger paths.

## Reproducibility Checklist

To reproduce an economic output exactly:

- same database input events/users/songs
- same snapshot period
- same `policy_id`
- same frozen snapshot metadata
- same deterministic allocator path

## Notes on Schema Compatibility

If working on an existing SQLite DB created before policy columns existed, schema compatibility helpers in scripts may add missing snapshot policy columns automatically.

For long-term production use, keep proper SQL migrations in sync.

## Recommended Future Enhancements

- Add explicit policy activation/deprecation metadata
- Add policy diff utility script for CLI reporting
- Add CI gate: run parity harness on every economics-related PR
- Add immutable policy changelog (who/why/when)
