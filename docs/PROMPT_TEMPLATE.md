# PROMPT_TEMPLATE.md

# 1. PURPOSE

This template ensures **consistent, high-quality interactions with LLMs**.

It injects:

- project context
- constraints
- expectations

---

# 2. MASTER PROMPT TEMPLATE

Use this as base for any request:

---

## SYSTEM CONTEXT

You are working on a project defined as:

[PASTE LLM_CONTEXT.md HERE]

---

## TASK

[Describe clearly what you want]

---

## CONSTRAINTS

- Do NOT break core principles
- Keep blockchain invisible
- Prioritize UX simplicity
- Align with user-centric economy
- Respect hybrid architecture

---

## OUTPUT FORMAT

[Define format: code, markdown, plan, etc.]

---

# 3. EXAMPLES

---

## Example 1 — Feature Design

TASK:

Design a playlist sharing feature.

CONSTRAINTS:

- must not turn into social media feed
- must reinforce music discovery
- must integrate with curator system

---

## Example 2 — Backend Design

TASK:

Design the stream event pipeline.

CONSTRAINTS:

- scalable to millions of users
- compatible with royalty system
- minimal blockchain interaction

---

## Example 3 — UX Design

TASK:

Design onboarding flow.

CONSTRAINTS:

- <30 seconds
- no blockchain exposure
- immediate music playback

---

# 4. ADVANCED MODE (VERY IMPORTANT)

When working on complex tasks, add:

---

## THINKING MODE

Before answering:

1. Identify which system is affected:
   - streaming
   - economic
   - cultural
   - trust

2. Evaluate trade-offs

3. Ensure alignment with LLM_CONTEXT

---

# 5. ITERATION MODE

When refining outputs:

- ask for improvements
- request simplification
- challenge assumptions
- compare alternatives

---

# END OF FILE