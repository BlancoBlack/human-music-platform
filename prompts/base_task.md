# Base task prompt — HumanSounds (mandatory for all work)

**Usage:** Attach or paste this file **with** every Cursor task. Domain-specific prompts (`backend_task.md`, etc.) **add** constraints; they **never** override this file.

---

## 1. System context (short)

HumanSounds is a production-grade stack: **FastAPI** backend, **streaming ingestion**, **economics (ledger V2)**, **discovery**, **JWT auth**, and a **state documentation layer** under `docs/state/`. Implementation in the repository is authoritative.

---

## 2. Task

<!-- Replace the line below with the concrete task before sending to the agent. -->

**TASK:** _[Describe the change, bugfix, or investigation here]_

---

## EXECUTION MODE & MODEL SELECTION

Use task intent to choose execution posture before doing work:

- **Implementation mode (default):** when the request asks to add/edit/fix code or docs with clear scope. Execute directly, keep reasoning concise, and ship the change end-to-end.
- **Analysis mode:** when the request asks for understanding, architecture options, comparison, or audit/review without immediate code changes. Focus on evidence, trade-offs, and explicit recommendations.
- **Debug mode:** when symptoms are known but root cause is uncertain. Reproduce, isolate cause, then implement and verify the fix if requested.

Task interpretation guide:

- **Analysis tasks:** prioritize reasoning depth and structured findings; do not imply implementation happened unless files were actually changed.
- **Implementation tasks:** prioritize execution and verification; avoid overlong planning when scope is already clear.
- **Debugging tasks:** prioritize runtime facts, logs, and code-path tracing; include residual risk if unresolved.

Model/tool routing guidance (execution-authoritative in this prompt layer):

- Prefer a **reasoning-first pass** for unclear problems, architecture decisions, and complex multi-system debugging.
- Prefer an **execution-first pass** for straightforward implementation/refactor tasks with clear acceptance criteria.
- For mixed tasks, run a short reasoning pass first, then execute in the same task turn.
- Always enforce sections **A/B/C** below regardless of chosen mode.

---

## A) STATE LAYER MAINTENANCE — **MANDATORY — NOT OPTIONAL**

After completing the task (same session, before marking work done):

1. **Update** `/docs/state/` — only files and **sections affected** by the change (e.g. `streaming.md` for ingest changes). Do **not** rewrite unrelated files.
2. **Preserve** the canonical section structure in every updated state file:
   - `## CURRENTLY IMPLEMENTED`
   - `## PARTIALLY IMPLEMENTED`
   - `## NOT IMPLEMENTED`
   - `## KNOWN ISSUES`
3. **Rules:**
   - **New behavior shipped in code** → reflect under **CURRENTLY IMPLEMENTED** (and trim stale bullets elsewhere if they contradict code).
   - **Incomplete / flag-gated / dialect-specific** → **PARTIALLY IMPLEMENTED** with precise scope.
   - **Removed or never existed in repo** → **NOT IMPLEMENTED** or delete obsolete claims.
   - **Bugs, gaps, or doc/code tension** → **KNOWN ISSUES** with neutral wording.
   - **Code overrides docs** — if docs and code disagree, **fix the docs** to match code (or fix the code if the task is to correct behavior; then document the new truth).
   - **Ambiguity after reading the repo** → mark **UNKNOWN** in the appropriate section; do not invent behavior.

**Skipping `/docs/state/` updates is a failed task.** Partial tasks still require partial doc touch-ups when behavior changed.

---

## B) CONSISTENCY CHECK — **MANDATORY — NOT OPTIONAL**

Before editing state docs, **verify** implementation against the codebase for the areas this task touches:

| Area | When to check |
|------|----------------|
| **Streaming** | Any change to `/stream`, sessions, checkpoints, `ListeningEvent`, validation, aggregates, workers touching listens |
| **Economics** | Any change to payouts, snapshots, `payout_lines`, settlements, previews, `UserBalance`, distribution, pool model |
| **Discovery** | Any change to `/discovery/home`, ranking, pools, hydration, caps |

If verification finds **mismatch** between prior state docs and code:

- **Correct the state docs** to match code **or** document the defect under **KNOWN ISSUES** if the code is wrong and the task intentionally leaves it unfixed.

---

## C) OUTPUT REQUIREMENT — **MANDATORY — NOT OPTIONAL**

The agent’s **final response** must include:

1. **Summary** of code/config changes (paths, behavior).
2. **State layer:** explicit list of **which** `docs/state/*.md` files were updated (or “none” only if the task truly did not affect implementation — e.g. typo-only in non-behavioral comment with **no** semantic drift; rare).
3. **Relevant excerpts or section titles** changed in state docs when practical (so reviewers can diff quickly).

**Delivering code without the state-layer portion of the output is incomplete work.**

---

## 3. General execution rules

- Prefer small, reviewable diffs; match existing project style.
- Do not rely on chat memory for system facts — **read** `docs/state/` and code.
- Do not document future plans inside `docs/state/` (state is **current implementation** only).
