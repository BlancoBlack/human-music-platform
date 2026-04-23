# Backend task prompt — HumanSounds

**Prerequisite:** Apply [`base_task.md`](./base_task.md) in full. Sections A–C there are **NOT OPTIONAL**.

---

## Domain: backend (FastAPI, API, DB, workers)

**TASK:** _[Backend-specific task here]_

### Additional constraints

- Routes, dependencies, and `main.py` wiring must stay consistent with OpenAPI reality; update `docs/state/backend.md` when endpoints, workers, DB bootstrap, or CORS change.
- Auth behavior changes → update `docs/state/auth.md` (even if the edit is in `deps.py` or `auth_routes.py`).
- Prefer Alembic migrations for schema; reflect model inventory in `backend.md` when tables/models are added or removed.

### Mandatory blocks (same as `base_task.md`; do not skip)

**A) STATE LAYER — NOT OPTIONAL:** Update affected `docs/state/*.md`; preserve the four standard sections; code wins over stale prose.

**B) CONSISTENCY — NOT OPTIONAL:** Re-read code for streaming/economics/discovery touchpoints before writing state docs; mismatches → fix docs or file under **KNOWN ISSUES**.

**C) OUTPUT — NOT OPTIONAL:** Final reply must list updated state files and summarize doc edits.
