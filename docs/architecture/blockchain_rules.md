<!-- model: claude -->
# Blockchain Rules

execution_routing.md has priority over this file

# Blockchain Rules (Algorand)

Blockchain integration is handled via:

backend/app/blockchain/algorand_client_v2.py

---

# Current State

- using localnet
- using test account
- sending simple transactions

---

# Rules

- Python Algorand client code stays in `backend/app/blockchain/`; contract sources belong under `blockchain/` (e.g. `blockchain/algorand/`) when you add them
- workers call blockchain
- services NEVER call blockchain

---

# Contracts

Smart contracts are not checked into this repo yet. When added, prefer a dedicated AlgoKit/Puya project under `blockchain/algorand/` (or `contracts/`) scoped to product needs—not a generic RWA template.

---

# Do NOT

- mix contract code with backend
- call blockchain from API routes