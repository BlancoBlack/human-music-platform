# Discovery task prompt — HumanSounds

**Prerequisite:** Apply [`base_task.md`](./base_task.md) in full. Sections A–C there are **NOT OPTIONAL**.

---

## Domain: discovery (ranking, pools, `/discovery/home`)

**TASK:** _[Discovery-specific task here]_

### Additional constraints

- Candidate pools, scoring, `finalize_discovery_ranking`, `compose_discovery_sections`, and hydration live in `backend/app/services/discovery_*.py` and `discovery_routes.py` — state docs must match actual formulas and constants.
- If editorial/community/reputation layers are still stubs, say so under **PARTIALLY IMPLEMENTED** or **NOT IMPLEMENTED** in `docs/state/discovery.md`; do not imply features that are not in code.

### Mandatory blocks (same as `base_task.md`; do not skip)

**A) STATE LAYER — NOT OPTIONAL:** Update `docs/state/discovery.md` (and `backend.md` if new routes or tags).

**B) CONSISTENCY — NOT OPTIONAL:** Verify discovery pipeline and API response shape in code before updating state docs.

**C) OUTPUT — NOT OPTIONAL:** Final reply must list updated state files and summarize doc edits.
