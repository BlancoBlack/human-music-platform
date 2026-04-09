<!-- model: claude -->

# Composer 2 Usage Rules

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

# Mandatory Rule

Claude MUST NOT generate or modify code directly in chat.

If code needs to be written or updated:

→ Claude must instruct to use Composer

---

# Required Workflow

1. Understand the task
2. Explain the approach
3. Validate architecture alignment
4. THEN instruct Composer to implement

---

# Example Behavior

Correct:

"To implement this feature, we should create a new service layer.

Use Composer to generate the following files:
- backend/app/services/user_service.py
- backend/app/models/user.py"

---

Incorrect:

(providing full code directly in chat)

---

# File Creation Rules

All new files must be created using Composer.

All modifications must be done using Composer.

---

# Architecture Protection

Composer 2 must follow:

- service layer separation
- event-driven system
- no business logic in routes
- no blockchain calls outside workers

---

# Enforcement

If a request involves code:

Claude must respond with:

→ explanation
→ file plan
→ explicit instruction to use Composer

---

# Goal

Maintain clean architecture and prevent uncontrolled code generation.