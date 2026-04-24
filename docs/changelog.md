# Changelog

## Latest Changes (Today)

### Auth & Register Improvements

- Canonical role system implemented and enforced in backend registration:
  - `role = user | artist`
  - `sub_role = artist | label`
- Legacy `role_type` payloads are normalized safely to canonical internal values.
- Invalid role/sub-role combinations are rejected with explicit `400` responses.
- Frontend artist/label UX now maps naming cleanly to backend contract (`username` and `artist_name` from the same name input for creator flow).
- Password hashing reliability restored by pinning bcrypt compatibility (`bcrypt==4.0.1`) and enforcing explicit password-length guardrails for bcrypt.

### Onboarding System

- End-to-end onboarding path is implemented:
  - register -> preferences -> first discovery session -> complete onboarding
- Backend onboarding state machine introduced and used by endpoints:
  - `REGISTERED -> PREFERENCES_SET -> DISCOVERY_STARTED -> COMPLETED`
- Strict state transitions are enforced by backend service logic.
- Idempotency and reentry behavior implemented:
  - repeated calls and same-or-ahead states are handled safely for onboarding endpoints.

### Frontend <-> Backend Sync

- Frontend onboarding route resolver introduced (`resolveOnboardingRoute`) and wired to backend onboarding step.
- Onboarding route guard added with public-route exemptions (`/register`, `/login`).
- Frontend onboarding flow now hard-syncs from backend `/auth/me` after key actions instead of relying on local assumptions.
- Player entry now validates onboarding step before calling first-session API to avoid invalid state calls.

### UX Improvements

- Register screen role selection refined:
  - centered, balanced button layout
  - improved visual weight and responsiveness
- Creator registration clarity improved:
  - duplicate name fields removed from creator flow
  - dynamic label for name input (`Artist Name` vs `Label Name`)
- Password UX upgraded:
  - show/hide toggle
  - lightweight real-time validation feedback
  - submit-time hard error state

### Audit Findings Captured

- Solid areas identified:
  - backend role normalization and validation
  - onboarding state machine core
  - endpoint-level transition gating
- Improvement areas identified:
  - route guard scope (avoid globally forcing route intent)
  - DB-level constraints for onboarding state
  - redundant frontend `/auth/me` refresh calls in some paths
- Broken/high-risk items identified and tracked:
  - overly broad frontend guard can override valid user navigation
  - temporary debug logs in runtime paths (removed in this update)
