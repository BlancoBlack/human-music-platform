Type: LLM
Status: UNKNOWN
Linked State: /docs/state/README.md
Last Verified: 2026-04-29

# PROMPT_TEMPLATE.md

# 1. PURPOSE

This file points to the **canonical prompt system** under **`/prompts/`**. Use it so every Cursor task stays aligned with **`/docs/state/`** (implementation source of truth).

**Obsolete pattern:** Pasting the full `LLM_context.md` as the only system block for implementation tasks — use **`prompts/base_task.md`** first; add `LLM_context.md` only when you need **principles / product constraints**.

---

# 2. REQUIRED FILES PER TASK

| Step | File |
|------|------|
| 1 | **`/prompts/base_task.md`** — **always** (STATE LAYER + CONSISTENCY + OUTPUT are **NOT OPTIONAL**) |
| 2 | One of **`/prompts/backend_task.md`**, **`discovery_task.md`**, **`economics_task.md`**, **`debug_task.md`** when the task fits that domain |
| 3 | **`/docs/workflow.md`** — human-readable loop (define task → prompt → execute → update state → review) |

---

# 3. MASTER PROMPT SHAPE

Paste or attach in this order:

```text
1) prompts/base_task.md (full file)
2) [optional] prompts/<domain>_task.md
3) TASK section: fill in the task placeholder from base_task.md
```

Optional product layer:

```text
4) For principles only: excerpt or attach docs/LLM_context.md (relevant sections)
```

---

## CONSTRAINTS (default)

- Do NOT break core principles in `LLM_context.md` when that file is attached.
- **`/docs/state/`** must be updated per **`base_task.md` section A** when code behavior changes — **cannot skip**.
- Run **`base_task.md` section B** consistency check before editing state docs for streaming / economics / discovery.
- Final output must satisfy **`base_task.md` section C** (list updated state files + summarize doc edits).

---

## OUTPUT FORMAT

As defined in **`prompts/base_task.md` section C** — code/config summary plus explicit state-doc update list.

---

# 4. EXAMPLES

Use the same task block as in **`prompts/base_task.md`**; add domain files when relevant (e.g. discovery ranking change → `prompts/discovery_task.md`).

---

# 5. ADVANCED MODE

Before answering, identify affected systems (streaming, economics, discovery, auth, backend) and read the matching **`docs/state/*.md`** plus code — not memory alone.

---

# END OF FILE

## Related State
- /docs/state/README.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/README.md
