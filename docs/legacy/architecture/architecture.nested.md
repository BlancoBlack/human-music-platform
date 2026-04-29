<!-- model: claude -->
# Architecture

This project follows an event-driven architecture.

# Architecture Rules

execution_routing.md has priority over this file

---

# Flow

Frontend → API → Service → Database → Event → Worker → Blockchain

---

# Backend Layers

api → HTTP layer  
services → business logic  
models → database schema  
events → event emission  
workers → async processing  
blockchain → external integration

---

# Rules

- No business logic in API routes
- No blockchain calls in routes
- All side effects go through events
- Workers execute async logic

---

# Blockchain

Algorand is used only for:

- transaction simulation
- future royalty logic

---

# Current Limitation

Event system is synchronous (in-process)

Future:

- Redis / queue system