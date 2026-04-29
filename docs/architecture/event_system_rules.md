Type: ARCHITECTURE
Status: UNKNOWN
Linked State: /docs/state/backend.md
Last Verified: 2026-04-29

<!-- model: claude -->
# Event System Rules

The system uses an internal event bus.

# Event System Rules

execution_routing.md has priority over this file

---

# Current Implementation

- in-process event dispatch
- synchronous execution

---

# Rules

- All side effects must go through events
- Services emit events
- Workers handle events

---

# Example

stream_created → worker → blockchain

---

# Future Evolution

Replace EventBus with:

- Redis queue
- message broker

---

# Do NOT

- call workers directly from routes
- execute side effects in services

## Related State
- /docs/state/backend.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/backend.md
