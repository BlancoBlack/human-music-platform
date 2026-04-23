# Development workflow — HumanSounds

This workflow is **mandatory** for engineering work tracked through Cursor (or any LLM-assisted task). It ties code changes to the **state layer** under `docs/state/`.

---

## Document hierarchy

| Path | Role |
|------|------|
| **`/docs/state/`** | **Single source of truth** for *what the codebase does today*. Updated after tasks that affect behavior or APIs. |
| **`/docs/architecture/`** (if present) | Intended design, boundaries, target shapes — may lag implementation. |
| **`/docs/product/`** (if present) | Ideas, narratives, non-binding specs. |
| **`/docs/tech-debt/`** (if present) | Known problems and cleanup backlog (may overlap **KNOWN ISSUES** in state docs; prefer state for “current bug truth”). |
| **`/docs/decisions/`** (if present) | Historical ADRs / decisions. |
| **`/prompts/`** | Reusable task templates; **`prompts/base_task.md`** is required for every task. |

**Rule:** When product or architecture docs disagree with **`docs/state/`** or the repo, **code + `docs/state/` win** until someone changes the code and updates state.

---

## Development loop (mandatory)

1. **Define the task** — scope, acceptance, affected subsystems (streaming, economics, discovery, auth, backend shell).
2. **Select a prompt template** from `/prompts/`:
   - Always include **`prompts/base_task.md`**.
   - Add **`backend_task.md`**, **`discovery_task.md`**, **`economics_task.md`**, or **`debug_task.md`** when the task is domain-heavy.
3. **Cursor (agent) executes** — code, tests, config as needed.
4. **Cursor updates `/docs/state/*`** — **NOT OPTIONAL** (see `prompts/base_task.md` section A). Only touched areas; preserve the four section headers per file.
5. **Developer reviews** — code diff + state diff + agent output listing updated state files.

---

## Rules (non-optional)

| Rule | Detail |
|------|--------|
| **Never run a task without a prompt template** | Minimum: attach **`/prompts/base_task.md`**. Domain prompts add constraints; they do not remove base rules. |
| **Never skip the state update** | If behavior or contracts changed, **`docs/state/`** must change in the same task. Skipping is a failed delivery. |
| **Never trust chat memory over state docs** | Re-read `docs/state/` and source when resuming work. |
| **STATE LAYER UPDATE IS NOT OPTIONAL** | Same as above; enforced by `base_task.md` sections A–C and this document. |
| **Consistency before writing state** | Follow **`base_task.md` section B** for streaming / economics / discovery when those areas are touched. |

---

## Related project docs

- **`docs/PROMPT_TEMPLATE.md`** — Points at `prompts/base_task.md` and the prompt system for structured requests.
- **`docs/LLM_context.md`** — Product philosophy and principles; **not** a substitute for `docs/state/`.
- **`docs/ai-rules/execution_routing.md`** — Model/tool routing; does not relax state-layer rules.

---

## Quick copy for a new Cursor chat

```text
Use prompts/base_task.md (mandatory). [+ prompts/backend_task.md if applicable]

TASK: <your task>
```

Replace the bracketed line with the appropriate domain prompt when relevant.
