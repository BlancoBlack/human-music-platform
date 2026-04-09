<!-- model: claude -->

# Coding Standards

execution_routing.md has priority over this file

---

# General

- small files
- explicit logic
- readable code

---

# Backend

- snake_case
- modular structure
- no hidden logic

---

# Frontend

- camelCase
- simple components
- avoid deeply nested components

---

# Architecture

- separation of concerns
- no cross-layer logic

---

# Priority

clarity > cleverness

---

# Code Generation Policy (CRITICAL)

This project enforces strict separation between reasoning and code generation.

---

# Core Principle

Claude is responsible for:

- reasoning
- architecture decisions
- explanations

Composer 2 is responsible for:

- writing code
- modifying files
- creating new modules

---

# Mandatory Rules

- Claude MUST NOT generate full code implementations directly in chat
- Claude MUST NOT modify files directly
- All code must be created or modified using Composer

---

# Required Workflow

1. Understand the task
2. Explain the approach
3. Validate architecture alignment
4. THEN instruct Composer to implement

---

# Correct Behavior

Claude should respond with:

- explanation of the solution
- list of files to create or modify
- instructions for Composer

---

# Incorrect Behavior

- providing full code implementations in chat
- modifying logic without Composer
- mixing explanation and full code output

---

# File Creation Rules

- All new files must be created using Composer
- All file modifications must be done using Composer

---

# Architecture Protection

Composer must always respect:

- service layer separation
- event-driven system
- no business logic in routes
- no database logic in routes
- no blockchain calls outside workers

---

# Goal

Maintain clean architecture, scalability, and controlled code generation.


# Execution Enforcement (CRITICAL)

If code is required:

Claude MUST NOT continue reasoning.

Claude MUST immediately output:

HANDOFF TO COMPOSER 2

No exceptions.