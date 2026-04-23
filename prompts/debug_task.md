# Debug task prompt — HumanSounds

**Prerequisite:** Apply [`base_task.md`](./base_task.md) in full. Sections A–C there are **NOT OPTIONAL**.

---

## Domain: debugging (defects, regressions, investigations)

**TASK:** _[Symptoms, repro steps, scope, and suspected area]_

### Additional constraints

- Prefer **evidence** from code, logs, and DB state over assumptions.
- If the bug is **confirmed** in code but **not fixed** in this task, add or extend **KNOWN ISSUES** in the relevant `docs/state/*.md` with reproduction scope.
- If the fix **changes behavior**, update **CURRENTLY IMPLEMENTED** / **PARTIALLY IMPLEMENTED** as appropriate.

### Mandatory blocks (same as `base_task.md`; do not skip)

**A) STATE LAYER — NOT OPTIONAL:** Any behavior clarification discovered during debugging must be reflected in `docs/state/` (even if code is unchanged but docs were wrong).

**B) CONSISTENCY — NOT OPTIONAL:** Re-verify streaming, economics, and/or discovery logic in code for the affected subsystem before editing state docs.

**C) OUTPUT — NOT OPTIONAL:** Final reply must list updated state files (or explicitly state no doc update was needed because **only** non-behavioral understanding changed — rare) and summarize doc edits.
