<!-- model: claude -->

# Execution Routing (CRITICAL)

This rule controls which system executes each task.

---

# Priority

This rule OVERRIDES all other rules.

---

# Model Roles

Claude:
- reasoning
- architecture decisions
- planning
- debugging complex systems

Composer 2:
- ALL code generation
- ALL file creation
- ALL file modification
- ALL refactoring

---

# Task Classification

## Use Claude when:

- problem is unclear
- system design is needed
- architecture decisions are required
- debugging complex flows
- analyzing existing code

## Use Composer 2 DIRECTLY when:

- writing code
- editing files
- fixing bugs with clear scope
- refactoring
- implementing known patterns

---

# Hard Rule

If task == implementation:

→ SKIP Claude reasoning
→ USE Composer 2 immediately

---

# Handoff Protocol

When Claude is used:

Claude MUST end with:

HANDOFF TO COMPOSER 2:
- files to create/modify
- exact instructions

---

# Anti-Patterns

DO NOT:
- use Claude for simple implementations
- generate code inside Claude
- mix reasoning and coding