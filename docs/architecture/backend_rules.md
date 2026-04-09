<!-- model: claude -->
# Backend Rules

Backend uses FastAPI.

# Backend Rules

execution_routing.md has priority over this file

---

# Structure

api → routes only  
services → business logic  
models → SQLAlchemy models  
events → event emitters  
workers → background logic

---

# Rules

- Routes must be thin
- Services handle logic
- DB access only in services
- No direct DB usage in routes

---

# Stream Flow

1. create stream in DB
2. emit event
3. worker processes event

---

# Do NOT

- call blockchain from routes
- mix DB and API logic
- create large files