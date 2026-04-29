Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/streaming.md
Last Verified: 2026-04-29

# Tech debt: Ingestion

Listening pipeline: `POST /stream/start-session`, `POST /stream/checkpoint`, `POST /stream` (finalize), `ListeningSession`, checkpoints, and `ListeningEvent` as economic source of truth.

---

## Session recovery after full page refresh

**Description**  
The global player keeps `session_id`, sequence, and engagement state only in memory. A browser refresh drops client state while the server may still hold an open `listening_session` and checkpoints without a final `ListeningEvent`.

**Why it matters**  
Users refresh habitually; without recovery, segments of real listening can fail to finalize or leave orphan sessions—bad for integrity and analytics.

**Current behavior**  
No `sessionStorage` (or similar) persistence; no `GET` session API to resume. Finalize runs on `pagehide`/`beforeunload` with `keepalive` but cannot run after a hard refresh that tears down JS before the request completes.

**Proposed solution**  
- Persist minimal state: `{ session_id, song_id, next_sequence_hint, ... }` in `sessionStorage`.  
- Add a **read-only** backend endpoint (e.g. `GET /stream/session/{id}` or `GET /listening-sessions/{id}`) returning status, song binding, last checkpoint, finalized flag—enough to resume or safely abandon.  
- On load, reconcile: if session still active and matches current track intent, reattach; else finalize or discard per policy.

**Priority:** CRITICAL  

**When to address:** Before relying on ingestion for payouts at scale; ideally **post-MVP, pre-production hardening**.

---

## Finalize-after-410 policy (explicit product + server decision)

**Description**  
Checkpoint idle returns **410** `session_expired`. The client may still **finalize** the same `session_id` with accumulated engaged seconds; the backend does not currently tie finalize eligibility to checkpoint freshness.

**Why it matters**  
Economics and fraud teams need one story: does “session expired” mean “no more checkpoints” only, or “this listen segment must not become a `ListeningEvent`”?

**Current behavior**  
410 applies to **checkpoints** only. `POST /stream` with `session_id` is not rejected for checkpoint idle. Client finalizes after 410 when finalize succeeds, then starts a new session.

**Proposed solution**  
- **Product decision:** Allow or forbid finalize for idle-expired sessions.  
- If forbidden: enforce in `stream_service` / validation path (e.g. compare server time to last checkpoint or `started_at`).  
- If allowed: document in economics/README and keep client behavior aligned.

**Priority:** CRITICAL  

**When to address:** **Before payouts v2** or any audit that requires strict alignment between checkpoint trail and economic events.

---

## Enforce finalize vs checkpoint consistency on the backend

**Description**  
Today, checkpoint monotonicity, idle expiry, and idempotency are enforced in the checkpoint service; finalize uses separate rules (`validate_listen`, session ownership). There is no single invariant like “every finalized session must have had checkpoint continuity” unless product requires it.

**Why it matters**  
Reconciliation jobs, disputes, and ML features benefit from explicit, checkable invariants between `listening_session_checkpoints` and `listening_events`.

**Proposed solution**  
- Define invariants (e.g. max gap between last checkpoint and finalize timestamp; or require ≥1 checkpoint before finalize for hybrid clients).  
- Enforce in finalize path or via DB constraints/triggers only where safe.  
- Add integration tests and optional admin queries for violations.

**Priority:** CRITICAL (if payouts depend on hybrid proof); **HIGH** if MVP only needs honest duration.

**When to address:** **Post-MVP** once hybrid ingestion is default; tighten **before payouts v2**.

---

## Optional: reject finalize if session is “expired” (checkpoint idle)

**Description**  
Product may require that once checkpoint idle fires, the server **rejects** `POST /stream` for that `session_id`, forcing a new `start-session` for any new segment.

**Why it matters**  
Simplifies narrative (“expired = dead session”) and may reduce edge cases where duration is claimed without recent checkpoints.

**Current behavior**  
Idle is enforced at checkpoint only; finalize is independent.

**Proposed solution**  
If chosen: add `session_expired_at` or derive from last checkpoint + policy; return structured error (e.g. `finalize_session_expired`) from `POST /stream`. Client already knows how to start a new session after failures in some paths.

**Priority:** MEDIUM (optional product fork)  

**When to address:** After explicit **product/legal** sign-off; not required for all deployments.

---

## Orphan `listening_sessions` after failed `play()` or client crashes

**Description**  
`start-session` can succeed while `play()` never starts (or client dies before finalize). Server session rows exist without a matching `ListeningEvent`.

**Why it matters**  
Noise in ops, analytics, and any future “session cleanup” jobs; may complicate user-level session limits.

**Current behavior**  
Client clears refs and logs; server session remains open until finalized or manual cleanup.

**Proposed solution**  
- TTL or cron to mark/delete abandoned sessions without events after N hours.  
- Optional: lightweight `POST` to abandon session (documented as non-economic).

**Priority:** HIGH  

**When to address:** **Post-MVP**; before high-volume production traffic.

---

## `ListeningSession` is metadata for events today (not antifraud input)

**Description**  
Hybrid ingestion binds a `ListeningEvent` to a `ListeningSession` row (`session_id` on the event). **Checkpoint trails** and **session idle (410)** behavior are documented as **not** feeding `validate_listen`, daily caps, spacing, or payout weights—see `listening_checkpoint_service` module comment and `validate_listen` implementation (duration + repeat history only).

**Why it matters**  
Product may later want **session-based antifraud** (e.g. require recent checkpoints before a finalize counts), **session-scoped rate limits**, or **session analytics** tied to economics. Today, tightening the coupling would add complexity without changing economic outcomes.

**Current behavior**  
If the client supplies `listening_session_id`, the server checks the row exists and belongs to the user **before** acquiring the ingestion lock and calling `validate_listen`; `validate_listen` does **not** read session or checkpoint tables.

**Proposed solution**  
- If product requires it: define explicit rules (e.g. min checkpoints, max gap before finalize) and enforce in `stream_service` / validation path with tests.  
- Until then: keep treating sessions as **integrity/metadata** for the hybrid client, not an economic proof layer.

**Priority:** MEDIUM (optional product fork)  

**When to address:** Only when implementing session-based limits, antifraud, or analytics that must align with `ListeningEvent` semantics.

---

## Stream tracking maturity

**Description**  
Core listening/event intelligence exists but onboarding success loops are not deeply wired into product activation metrics.

**Why it matters**  
Without explicit activation instrumentation, onboarding and first-session changes are difficult to evaluate against real retention outcomes.

**Current behavior**  
Events, sessions, and aggregates are available, but onboarding activation tracking is not yet modeled as a first-class system.

**Proposed solution**  
Define onboarding activation metrics and wire stream-tracking outputs to those milestones.

**Priority:** HIGH  

**When to address:** Before scaling onboarding optimization work.

## Related State
- /docs/state/streaming.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/streaming.md
