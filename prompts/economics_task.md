# Economics task prompt — HumanSounds

**Prerequisite:** Apply [`base_task.md`](./base_task.md) in full. Sections A–C there are **NOT OPTIONAL**.

---

## Domain: economics (previews, ledger V2, settlement, payouts)

**TASK:** _[Economics-specific task here]_

### Additional constraints

- Distinguish **live previews** (`calculate_user_distribution`, pool APIs) from **ledger** (`payout_lines`, snapshots, settlements). Naming in docs must match symbols in code (e.g. `generate_payout_lines`, not informal aliases).
- Currency, batch status, and settlement `execution_status` values must match models and workers.
- Dashboard SQL and analytics helpers — update `docs/state/economics.md` when their behavior or data sources change.

### Mandatory blocks (same as `base_task.md`; do not skip)

**A) STATE LAYER — NOT OPTIONAL:** Update `docs/state/economics.md`; touch `backend.md` if new admin or payout routes appear.

**B) CONSISTENCY — NOT OPTIONAL:** Trace payout/snapshot/settlement code paths before documenting; mismatches → correct docs or **KNOWN ISSUES**.

**C) OUTPUT — NOT OPTIONAL:** Final reply must list updated state files and summarize doc edits.
