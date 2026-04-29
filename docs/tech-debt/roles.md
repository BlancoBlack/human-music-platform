Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/auth.md
Last Verified: 2026-04-29

# Tech debt: Roles, onboarding, and entry flows

This file groups cross-domain technical debt affecting onboarding, roles, and system entry flows.
Do NOT fragment these issues across multiple tech-debt files.

## High Priority Issues

- **Role System Duplication (user vs listener)**
  - Product/auth layer uses canonical role `user`, while RBAC still uses legacy role name `listener`.
  - A compatibility mapping layer is now used in user creation (`user -> listener`, `artist -> artist`) as a temporary stability fix.
  - Risks:
    - semantic confusion across API, RBAC, and tests
    - elevated chance of permission bugs from role-name drift
    - onboarding/payout flow coupling to legacy role vocabulary
  - Required future action:
    - perform full role migration to unified `user` role in RBAC
    - update RBAC seeds and existing DB role records
    - remove compatibility mapping after data migration

- **Frontend route guard scope is too broad**
  - Global onboarding guard can force users to `/player` or `/onboarding` from unrelated authenticated routes.
  - Needs route-scoped policy (only onboarding-critical routes should be hard-gated).

- **Missing DB-level constraint for onboarding state**
  - `users.onboarding_step` is currently a free string at DB level.
  - Application logic validates transitions, but DB should enforce allowed values to prevent out-of-band corruption.

- **Redundant `/auth/me` calls in frontend critical paths**
  - Some auth/onboarding flows call `/auth/me` multiple times in quick sequence.
  - Increases latency and can add avoidable flicker/network overhead.

## Medium Priority Improvements

- **Onboarding discovery mode is only lightly differentiated**
  - First-session endpoint reuses the core ranking pipeline with light boosts and filtering.
  - Product goal likely needs stronger cold-start and onboarding-specific ranking behavior.

- **Role semantics (`role` vs `sub_role`) need strict cross-layer consistency**
  - Backend canonical model is `role=user|artist` with `sub_role`.
  - Frontend copy and future feature work must not regress into treating `label` as a primary role.

- **UX consistency refinements**
  - Keep register/login/onboarding micro-interactions aligned with upload pipeline visual language.
  - Preserve low-friction onboarding while avoiding navigation surprises.

- **Missing slug support outside core entities**
  - Current clean-slug routing exists for `artist`, `album` (release), and `track` only.
  - Slug strategy is still missing for:
    - users
    - labels
    - curators
    - contributors
    - playlists
    - editorial posts
  - Follow-up work should define public URL ownership, mutability policy, history/redirect behavior, and canonical route families for each domain before those entities become SEO-facing.

## Known Bugs / Risks

- **Forced navigation risk from guard behavior**
  - If guard remains global and strict, authenticated users can be redirected away from valid non-onboarding routes.

- **Operational risk in SQLite dev/prod mismatch**
  - Some auth/locking behavior (e.g., refresh row-lock semantics) differs between SQLite and PostgreSQL.
  - Can hide concurrency issues until production-like environments.

## Related State
- /docs/state/auth.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/auth.md
