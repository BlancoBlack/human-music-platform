# Task launcher — HumanSounds

**Single entry point for running work in Cursor.** Do not paste ad-hoc prompts without going through this launcher.

---

## 1. Instructions for use

1. **Always start from this file** — copy the **Task template** (section 2), fill it in, then attach **both** files listed under “Prompts to attach.”
2. **Never run raw prompts** — do not paste only a task sentence; do not skip [`base_task.md`](./base_task.md).
3. **Always combine:**
   - **[`base_task.md`](./base_task.md)** — **every** task (mandatory execution contract: state layer, consistency, output).
   - **One domain prompt** when `DOMAIN` is not `general` — [`backend_task.md`](./backend_task.md), [`discovery_task.md`](./discovery_task.md), [`economics_task.md`](./economics_task.md), or [`debug_task.md`](./debug_task.md).

Optional human process reference: [`/docs/workflow.md`](../docs/workflow.md).

---

## 2. Task template

Copy, fill in, and paste **below** your attached prompts:

```text
TASK:
[Single clear goal: what changes or what must be true when done.]

DOMAIN:
[backend | discovery | economics | debug | general]

CONTEXT TO INCLUDE:
- State: [list paths under docs/state/, e.g. docs/state/streaming.md — only files that matter]
- Code: [optional: file paths or @-references; small snippets if paste — not the whole repo]

OUT OF SCOPE:
[What this task must not change, if any]
```

**Prompts to attach**

| DOMAIN    | Attach |
|-----------|--------|
| general   | `prompts/base_task.md` only |
| backend   | `prompts/base_task.md` + `prompts/backend_task.md` |
| discovery | `prompts/base_task.md` + `prompts/discovery_task.md` |
| economics | `prompts/base_task.md` + `prompts/economics_task.md` |
| debug     | `prompts/base_task.md` + `prompts/debug_task.md` |

---

## 3. Execution rules (strict)

| Rule | Requirement |
|------|-------------|
| Base contract | **`base_task.md` is ALWAYS required.** |
| Domain | **Domain prompt is required when `DOMAIN` is not `general`.** If multiple domains apply, pick the **primary** risk surface and attach that domain file; mention secondary areas in `TASK` or `CONTEXT`. |
| State layer | **NEVER skip STATE LAYER MAINTENANCE** (section A of `base_task.md`). |
| Context | **NEVER run without context** — at minimum, list relevant `docs/state/*.md` paths in `CONTEXT TO INCLUDE`; for code-heavy work, list concrete file paths or symbols. |

Violating any row above is an incomplete handoff. See **FAILURE CONDITIONS** below.

---

## FAILURE CONDITIONS (MANDATORY)

A run is **FAILED** (do not treat as done; redo the handoff) if **any** of the following is true:

| # | Condition |
|---|-------------|
| 1 | **`/docs/state/*` not updated when required** — behavior, API contracts, or operational semantics changed in code/config and the affected state file(s) were not brought in sync (per section A of `base_task.md`). |
| 2 | **State updates inconsistent with code** — prose in `docs/state/` contradicts the merged implementation (code wins; stale or wrong state is a failure until corrected or flagged under **KNOWN ISSUES** with intent). |
| 3 | **Required context missing** — no usable `CONTEXT TO INCLUDE` (see **MINIMUM VALID TASK**); vague task with no state path, no code pointers, and no explicit constraints. |
| 4 | **`base_task.md` not applied** — contract sections A–C not in scope for the agent (file not attached / not followed). |
| 5 | **Domain prompt skipped when needed** — `DOMAIN` is not `general` but the matching `*_task.md` was not attached, or the wrong domain file was used to hide scope. |

---

## MINIMUM VALID TASK

A handoff is **acceptable to run** only if **all** of the following hold:

| Requirement | Bar |
|-------------|-----|
| **TASK** | **Specific** — one clear outcome or change set; not a vague theme (“improve backend”). |
| **DOMAIN** | **Defined or inferable** — set explicitly in the template, or obvious from `TASK` such that the correct `*_task.md` (or `general`) is unambiguous. |
| **CONTEXT** | Under `CONTEXT TO INCLUDE`, provide **at least one** of: (a) a **`docs/state/*.md`** path that grounds the work, **or** (b) a **non-empty explicit constraint** block (e.g. env flags, invariants, “read-only investigation”, file/symbol list) sufficient to bound scope when no state file applies yet. Pure “do something” with empty context is **not** valid. |

---

## 4. Domain selection guide

| DOMAIN | Use when work primarily touches |
|--------|----------------------------------|
| **backend** | FastAPI routes, `main.py`, deps, DB/session/migrations, RQ/workers, CORS/static mounts, cross-cutting API behavior. |
| **discovery** | `/discovery/home`, candidate pools, scoring, ranking, section composition, hydration, discovery-related services or routes. |
| **economics** | User-centric preview, global pool, `payout_lines`, snapshots, batches, settlement, Algorand settlement path, dashboard payout SQL, split rules affecting money. |
| **debug** | Reproducing defects, tracing inconsistencies, fixing bugs where root cause is unclear; still update state if docs or behavior were wrong. |
| **general** | Repo-only hygiene with **no** behavior change (e.g. comment typo with zero semantic impact). Rare — when in doubt, pick a domain. |

---

## 5. Context minimization rule

- Include **only** `docs/state/` files that the task can invalidate or that define contracts you are touching (often **one** file; sometimes two if auth + backend, etc.).
- **Do not** dump the whole project, full trees, or entire large files — use **paths + section names** or short excerpts.
- **Prioritize:** (1) listed state files, (2) public interfaces (route signatures, schemas), (3) explicit constraints from `TASK` / `OUT OF SCOPE`.

---

## 6. Examples

### Example 1 — backend feature

```text
TASK:
Add a GET /health endpoint returning { "status": "ok" } for load balancers.

DOMAIN:
backend

CONTEXT TO INCLUDE:
- State: docs/state/backend.md
- Code: backend/app/main.py, backend/app/api/routes.py (or new router file if used)

OUT OF SCOPE:
Discovery, economics, auth flows.
```

**Attach:** `base_task.md` + `backend_task.md`

---

### Example 2 — bug fix

```text
TASK:
Fix incorrect pending payout cents on artist dashboard HTML; align with payout_lines + batch status in code.

DOMAIN:
debug

CONTEXT TO INCLUDE:
- State: docs/state/economics.md
- Code: backend/app/services/artist_dashboard_service.py, backend/app/api/routes.py (artist-dashboard handler)

OUT OF SCOPE:
Changing settlement worker or discovery.
```

**Attach:** `base_task.md` + `debug_task.md`

---

### Example 3 — discovery tuning

```text
TASK:
Adjust explore section soft-bucket thresholds; keep artist caps and section sizes unchanged.

DOMAIN:
discovery

CONTEXT TO INCLUDE:
- State: docs/state/discovery.md
- Code: backend/app/services/discovery_ranking.py (compose_discovery_sections / bucket helpers)

OUT OF SCOPE:
Candidate pool SQL, auth, economics.
```

**Attach:** `base_task.md` + `discovery_task.md`

---

## Quick checklist before sending

- [ ] `base_task.md` attached  
- [ ] Domain prompt attached if `DOMAIN` ≠ `general`  
- [ ] Section 2 template filled; state paths listed under `CONTEXT TO INCLUDE`  
- [ ] Agent will be able to satisfy **section C** of `base_task.md` (state files touched listed in final output)
