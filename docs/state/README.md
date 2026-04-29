# State documentation (`docs/state/`)

## What these docs are

- **State docs** describe the **current implementation** of HumanSounds as it exists in this repository: APIs, services, data models, workers, and cross-cutting behavior that code actually runs today.
- They are written by **reading the codebase** (FastAPI app under `backend/app/`, Alembic migrations, workers, frontend only where it directly reflects backend contracts).

## Single source of truth for “what runs”

- For questions like *“does ledger V2 exist?”*, *“how does refresh work?”*, *“what validates a stream?”* — **trust `docs/state/` and the code**, not informal narrative or older product notes.
- **Architecture or product** documents elsewhere may describe intent, roadmap, or naming that diverged from shipping code. When they disagree with `docs/state/` or with the repo, **the repo wins**.

## Difference vs architecture / product docs

| Aspect | State docs (`docs/state/`) | Typical architecture docs |
|--------|-----------------------------|----------------------------|
| Scope | What is implemented **now** | Target design, boundaries, evolution |
| Accuracy | Grounded in files and symbols | May lag refactors or renames |
| Futures | Omitted by rule | Often include planned phases |

## Maintenance requirement

- **Process:** follow **`/docs/system/workflow.md`** and **`/prompts/base_task.md`** for every behavior-changing task (state updates are **mandatory** there).
- **Update state docs when behavior changes** in a way users or operators would notice: new routes, auth flows, discovery rules, economics tables, settlement, streaming validation, etc.
- Small refactors with no behavioral change do not require edits.
- If implementation is ambiguous from code alone, state docs should say **UNKNOWN** rather than inferring.

## File index

| File | Focus |
|------|--------|
| [backend.md](./backend.md) | App composition, routes (by domain), workers, DB model inventory |
| [auth.md](./auth.md) | JWT, refresh rotation, cookies, deps, legacy header, impersonation |
| [streaming.md](./streaming.md) | `/stream`, sessions, checkpoints, validation, aggregates |
| [discovery.md](./discovery.md) | `/discovery/home`, pools, scoring, caps, gaps vs “four layers” |
| [economics.md](./economics.md) | User-centric preview, global pool, ledger V2, settlement |

## KNOWN ISSUES

- [LOW][DOC INCONSISTENCY] /docs/llm/PROMPT_TEMPLATE.md

  Expected (state):
  Documentation paths should resolve to current docs hierarchy.

  Found (doc):
  Document references missing path `/docs/workflow.md`.

- [LOW][DOC INCONSISTENCY] /docs/system/LLM_context.md

  Expected (state):
  Documentation paths should resolve to current docs hierarchy.

  Found (doc):
  Document references missing path `/docs/workflow.md`.

- [DOC INCONSISTENCY] /docs/llm/PROMPT_TEMPLATE.md contradicts current implementation:
  - Expected (state): documentation paths must resolve to current /docs hierarchy.
  - Found (doc): references missing path `/docs/workflow.md`.
- [DOC INCONSISTENCY] /docs/system/LLM_context.md contradicts current implementation:
  - Expected (state): documentation paths must resolve to current /docs hierarchy.
  - Found (doc): references missing path `/docs/workflow.md`.
