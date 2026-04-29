Type: ARCHITECTURE
Status: UNKNOWN
Linked State: /docs/state/frontend.md
Last Verified: 2026-04-29

<!-- model: claude -->
# Frontend Rules

execution_routing.md has priority over this file
Frontend uses Next.js App Router.

---

# Structure

app/page.tsx → main UI

---

# Rules

- frontend must call backend via fetch
- no business logic in UI
- no blockchain logic in frontend

---

# Interaction Flow

button → API call → backend → event → worker → blockchain

---

# Future

- split UI into components
- add hooks for API calls
- add state management

---

# Do NOT

- connect directly to blockchain
- duplicate backend logic

## Related State
- /docs/state/frontend.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/frontend.md
