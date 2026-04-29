# Tech debt: Backend

API services, SQLite-oriented patterns, and scale assumptions. Economic validation (`validate_listen`, `ListeningEvent`) is intentionally out of scope unless noted.

---

## Distributed / shared rate limiting (currently in-memory)

**Description**  
`POST /stream`, checkpoint, and start-session rate limits use **process-local** deques (`threading.Lock` + dicts). Multiple uvicorn workers or horizontal replicas do **not** share counters.

**Why it matters**  
Under production load balancers, per-IP/user limits become porous; abuse and accidental self-DOS risk rise.

**Current behavior**  
Correct for single-process dev; documented in code comments for SQLite vs Postgres.

**Proposed solution**  
- Redis (or similar) sliding windows keyed by user / IP / route class.  
- Or centralized gateway (API Gateway, Cloudflare) for coarse limits + app-level fine limits.

**Priority:** HIGH  

**When to address:** **Before multi-instance production** or public launch at scale.

---

## Full-text / trigram search for artist (and catalog) scaling

**Description**  
Artist search and listing may need FTS, trigram (`pg_trgm`), or dedicated search (OpenSearch, Meilisearch) as catalogs grow.

**Why it matters**  
SQLite `LIKE` and simple indexes do not scale to fuzzy, ranked search.

**Current behavior**  
`GET /artists/search` uses case-insensitive substring `LIKE '%query%'`. **Detailed write-up:** implementation, limitations, option matrix (Postgres pg_trgm, SQLite FTS5, external search), rough scale thresholds, mitigations (`limit`, debounce, max query length), and upgrade triggers are documented in [search_scalability.md](./search_scalability.md).

**Proposed solution**  
- Pick stack (stay SQLite + FTS5 vs Postgres vs external index); migrate query layer; add relevance ranking.  
- Use [search_scalability.md](./search_scalability.md) as the technical reference when executing.

**Priority:** MEDIUM  

**When to address:** When artist/song count or query latency crosses an agreed SLO (**post-MVP**); see triggers in [search_scalability.md](./search_scalability.md).

---

## Stronger session lifecycle model (`active` / `expired` / `finalized`)

**Description**  
`listening_sessions` has `finalized_at`, `song_id`, timestamps, but no explicit **state machine** column enforced everywhere. Checkpoint expiry and finalize eligibility are inferred from timestamps and triggers.

**Why it matters**  
Clear states simplify APIs, admin tools, and client recovery (“can I still checkpoint this id?”).

**Current behavior**  
Implicit: finalized if `finalized_at` set or `ListeningEvent` exists; checkpoint 410 if idle.

**Proposed solution**  
- Add `status` enum + transitions (e.g. `active` → `expired` on first 410 path server-side optional, `finalized` on event insert).  
- Migrate + backfill from existing data.

**Priority:** MEDIUM  

**When to address:** **Post-MVP**; pairs with **ingestion policy** and **session recovery API**.

---

## Optional checkpoint validation tightening

**Description**  
Further rules could bind `position_seconds` to song duration, detect impossible jumps, or correlate with engaged time server-side (heuristics only—client remains untrusted).

**Why it matters**  
Extra fraud signals without changing economic source of truth (`ListeningEvent`).

**Current behavior**  
Checkpoints store sequence + position; no strong correlation to master duration beyond client honesty.

**Proposed solution**  
- Soft warnings / flags on row or side table.  
- Hard reject only with product approval (could break legitimate clients).

**Priority:** LOW  

**When to address:** **Fraud review phase**; not blocking MVP.

---

## PostgreSQL ingestion serialization (multi-writer)

**Description**  
`stream_service` documents TODO: SQLite uses `ingestion_locks`; other dialects may not serialize `(user_id, song_id)` writers equivalently.

**Why it matters**  
Race conditions could theoretically produce two valid-looking events without proper locking under Postgres.

**Current behavior**  
- **SQLite (today):** `ingestion_locks` upsert serializes writers per `(user_id, song_id)` before `validate_listen` + `ListeningEvent` insert—**safe for current MVP** on a single-node SQLite deployment.  
- **Non-SQLite:** logs `ingestion_lock_skipped_unsupported_dialect` and **does not** apply an equivalent lock—**intentionally deferred** until Postgres is a real target, because a correct fix needs dialect-specific code paths (`FOR UPDATE` / advisory locks), preserved observability (`ingestion_lock_*` logs), and **concurrent integration tests** on both dialects (see module comment in `stream_service.py`).

**Proposed solution**  
Implement `FOR UPDATE` or advisory locks as spec’d in `stream_service.py` TODO; treat this as part of a broader **infra hardening pass** when migrating off SQLite (pairs with [infra.md](./infra.md)).

**Priority:** CRITICAL for **Postgres production**  

**When to address:** **Before** switching economic traffic to Postgres multi-worker.

---

## Analytics consistency rules (soft delete)

**Description**  
User-facing analytics queries must exclude soft-deleted songs (`Song.deleted_at IS NOT NULL`) so that catalog, discovery, and analytics surfaces stay aligned. Financial/payout queries must **not** filter `deleted_at`.

**Current behavior (implemented)**  
- `analytics_service.py`: all user-facing functions (`get_artist_streams_over_time`, `get_artist_top_songs`, `get_artist_top_fans`, `get_artist_insights`) join `Song` with `Song.deleted_at.is_(None)`.
- Discovery, catalog, streaming, and listening services also filter `deleted_at`.
- Payout services (`payout_service`, `snapshot_service`, `settlement_worker`) do **not** filter and must remain unmodified.

**Rule for new queries**  
Any new query that surfaces song data to users must include `Song.deleted_at.is_(None)`. Financial/audit queries must not.

**Priority:** N/A (implemented; maintain as invariant)

---

## Credit roles: `CHECK (role IN (...))` vs normalized `credit_roles` / enum

**Description**  
`song_credit_entries.role` is constrained with a SQL `CHECK` and mirrored allow-lists in Python (`CREDIT_ROLE_VALUES`) and the upload UI (`CREDIT_ROLES` in `UploadWizard`). This is **correct and consistent today**, but extending roles (e.g. songwriter, label) requires coordinated migrations + app changes in multiple places.

**Why it matters**  
Long-term catalog and royalty metadata will need **more credit types** and possibly **non-artist parties**; a single string column + widening `CHECK` becomes brittle.

**Current behavior**  
Fixed set: musician, mix_engineer, mastering_engineer, producer, studio, songwriter, sound_designer — enforced at DB `CHECK` + API `CREDIT_ROLE_VALUES` + frontend `CREDIT_ROLES`.

**Proposed solution**  
- Postgres: native `ENUM` or lookup table `credit_roles` with FK.  
- Keep human labels for display; version migrations when adding roles.

**Priority:** MEDIUM  

**When to address:** When upload metadata expands (see [ux.md](./ux.md) upload pipeline) or when standardizing on Postgres.

---

## Per-song industry identifiers (ISRC, ISWC, on-chain logical id)

**Description**  
No first-class fields or generation pipeline for **ISRC**, **ISWC**, or a **stable blockchain-compatible identifier** per recording/composition today.

**Why it matters**  
Cross-platform attribution, PRO registration, and future on-chain anchoring need immutable, industry-standard or platform-generated IDs—not only internal integer `song.id`.

**Current behavior**  
Internal surrogate keys only; identifiers are not assigned at end of upload.

**Proposed solution**  
- Schema: nullable `isrc`, `iswc`, `platform_work_id` (or similar) with validation formats.  
- Pipeline: generate or capture IDs after master is finalized; document precedence (artist-supplied vs minted).

**Priority:** MEDIUM (HIGH when entering label/PRO integrations)

**When to address:** After core upload + economics stability; before external registry or chain proofs depend on them.

---

## Release Auto-Publish Scheduler (Polling-based)

**Current implementation**  
Release scheduling uses a polling loop inside `backend/worker.py`:
- interval-based execution (env: `RELEASE_AUTO_PUBLISH_INTERVAL_SECONDS`, default 45s)
- calls `publish_due_releases(db)` in `app/services/release_service.py`
- query + update rule: `state='scheduled' AND discoverable_at <= now` -> `state='published'`

**Problems**  
- Not real-time: publish delay can be up to polling interval.
- Inefficient polling: wakes and queries even when no releases are due.
- Not safe for multi-worker / multi-instance deployment without coordination.
- No distributed locking / leader election for exactly-once scheduler semantics.

**Future solution**  
Replace in-process polling with one of:
- single-instance cron job
- distributed scheduled jobs (RQ/Celery scheduler)
- event-driven scheduler component

**Migration path**  
- Keep `publish_due_releases` as the idempotent core transition function (already satisfied).
- Extract invocation into standalone scheduled job runner.
- Disable in-worker polling loop once scheduler job is active.

---

## RBAC role linkage uses string instead of foreign key

**Description**  
Current RBAC linkage depends on `user_roles.role` (string) matching `roles.name` instead of a fully enforced FK path. This is not referentially safe and can create silent mismatches where `/auth/me.roles` contains a role string that does not resolve to permissions.

**Current mitigation**  
- Runtime validation for assignment paths (`validate_role_exists`).
- Warning logs when stored `user_roles.role` values do not match `roles.name`.
- Transitional nullable `user_roles.role_id` FK column is now present for forward migration prep.

**Planned solution**  
Migrate to normalized linkage using `user_roles.role_id` (FK to `roles.id`) and remove dependence on string-based joins for permission resolution.

**Migration plan (high-level)**  
1. Backfill `role_id` from `role` where names match.  
2. Switch joins/read paths to `role_id`.  
3. Enforce `role_id NOT NULL` once backfill + dual-write period is stable.  
4. Remove string-join dependency (`user_roles.role` no longer authoritative for linkage).

**Priority:** MEDIUM  

**When to address:** After compatibility window closes; before broader RBAC expansion and strict authorization rollout.

---

## Artist ownership lifecycle not defined (user deletion)

**Current behavior**  
`artists.owner_user_id` uses a nullable FK to `users.id` with `ON DELETE SET NULL`. If an owner user row is deleted, owned artists become unowned (`owner_user_id = NULL`) and no automatic transfer policy runs.

**Risks**  
- Ownership can be silently lost for active artist entities.  
- Authorization paths that rely on ownership (`edit_own_artist`) may deny all non-admin edits after deletion.  
- Operational ambiguity: no canonical actor is responsible for orphaned artists.

**Possible strategies**  
- **Transfer ownership** during deletion workflow (explicit target user/service account).  
- **Soft-delete users** and keep owner rows addressable for auditability.  
- **Prevent deletion** when ownership exists unless transfer is completed.

**Recommended future direction**  
Adopt a transfer-first lifecycle: block hard deletion of users with owned artists unless ownership is reassigned (or user is soft-deleted). Keep explicit audit trail for ownership moves.

**Priority:** MEDIUM  

**When to address:** Before endpoint-level ownership enforcement is turned on for write operations.

---

## Payment onboarding after registration (subscription state transition)

**Description**  
Registration currently ends at account + role/entity bootstrap. There is no payment onboarding step that transitions a regular user into a subscribed/paying state.

**Why it matters**  
Without explicit billing/subscription onboarding, product access tiers and future paid entitlements cannot be enforced consistently.

**Current behavior**  
Users can register and authenticate without any subscription setup flow; onboarding skips billing entirely.

**Future solution**  
- Introduce post-registration subscription setup flow.  
- Add billing provider integration and subscription lifecycle states.  
- Model and expose user state transition from free user to paying user.

**Priority:** HIGH  

**When to address:** Before launching paid features or subscription-gated product surfaces.

---

## Contributor role model for industry participants

**Description**  
Contributors (producers, engineers, managers, and similar participants) are not first-class platform identities in current role/onboarding models.

**Why it matters**  
Contributor identity is needed for richer credit graphs, royalty attribution, verification relationships, and future role-specific permissions.

**Current behavior**  
Song credit rows exist, but no dedicated contributor profile/onboarding model links contributor identity across songs/artists.

**Future solution**  
- Add contributor profile model and onboarding path.  
- Link contributors to songs/artists as reusable identities.  
- Prepare contributor payout eligibility and settlement integration.

**Priority:** MEDIUM-HIGH  

**When to address:** During next catalog/rights expansion, before contributor-side payout rollout.

---

## Curator role as upgrade flow from user

**Description**  
`curator` is not part of the registration role flow and lacks dedicated onboarding/profile support.

**Why it matters**  
Curation is a distinct product function (playlists, editorial content, discovery influence) and should be a controlled upgrade path from regular users.

**Current behavior**  
Curator capabilities are not initialized through `/auth/register`; no dedicated curator onboarding page/profile exists.

**Future solution**  
- Add explicit user-to-curator upgrade journey.  
- Add curator profile model similar in structure to artist onboarding.  
- Support curator playlist/editorial workflows and discovery impact tracking.

**Priority:** HIGH  

**When to address:** Before scaling editorial/discovery programs tied to curator performance.

---

## Label-artist collaboration and delegation model

**Description**  
Current label onboarding assumes straightforward ownership, but does not model nuanced artist-label collaboration contracts.

**Why it matters**  
Real label operations require partial control, delegated permissions, and artist approvals for release and metadata actions.

**Current behavior**  
Label entity ownership exists, but no explicit collaboration relationship model, delegation matrix, or artist approval workflow.

**Future solution**  
- Add normalized artist-label relationship model.  
- Add permission delegation rules per relationship scope.  
- Add release approval workflow with artist-side consent states.

**Priority:** HIGH  

**When to address:** Before multi-party label operations are opened in production.

---

## Artist verification system (multi-layer trust and rights checks)

**Description**  
No platform-level artist verification system currently exists.

**Why it matters**  
Verification is required for trust signaling, rights confidence, anti-fraud controls, and permission tiering as the platform scales.

**Current behavior**  
There are no verification badges, no trust tier outputs, and no identity/rights verification pipeline.

**Future solution**  
- **Basic verification**: social linking + metadata consistency checks.  
- **Official verification**: KYC-lite identity and distributor/PRO matching.  
- **Rights verification**: contract evidence, ownership proof, and audio fingerprint checks.  
- **Advanced verification**: identity graph and hybrid verification scoring.

**Expected output model**  
- Verification badges for user-facing trust signals.  
- Permission tiers unlocked by verification level.

**Priority:** HIGH  

**When to address:** Foundational for artist trust/risk controls; should start before broad creator onboarding expansion.

---

## Onboarding enforcement system (progressive unlock gates)

**Description**  
`users.onboarding_completed` exists, but backend routes do not yet enforce onboarding-completion gates.

**Why it matters**  
Without enforcement, onboarding status is informational only and cannot protect critical flows or progressive product unlocks.

**Current behavior**  
Onboarding state is set during registration, and helper logic exists for upload-cap decisions, but route-level blocking/unlock remains disabled.

**Future solution**  
- Enforce onboarding gates on selected actions until completion.  
- Add guided onboarding UX states and step tracking.  
- Implement progressive unlock model tied to onboarding milestones.

**Priority:** MEDIUM  

**When to address:** After onboarding UX steps are stabilized and before relying on onboarding state for policy/compliance.

---

## Slug schema hardening deferred for SQLite-safe migration path

**Description**  
Public slug rollout keeps `artists.slug`, `releases.slug`, and `songs.slug` nullable in migration `0018_public_entity_slugs` to avoid SQLite table-rebuild operations.

**Why it matters**  
Enforcing `NOT NULL` on existing SQLite tables can require table rebuild semantics (`batch_alter_table`) and may fail or become risky in FK-heavy schemas.

**Current behavior**  
Slug columns are added additively, backfilled, and uniqueness is enforced with a dialect-safe strategy (unique constraint on non-SQLite, unique index fallback on SQLite). `NOT NULL` is intentionally deferred.

**Proposed solution**  
Add a future dialect-aware hardening migration to enforce `NOT NULL` where safe (or after production DB standardization), with explicit prechecks for null rows.

**Priority:** MEDIUM  

**When to address:** During schema-hardening phase after SQLite compatibility constraints are no longer required.

---

## Public audio exposure via static `/uploads`

**Description**  
Public endpoints (e.g. `/artist/{slug}/tracks`, `/artist/{slug}/releases`) expose `audio_url` values pointing to static `/uploads/...` paths served via `StaticFiles`.

These URLs are:
- long-lived
- unauthenticated
- directly accessible

UI-level auth gating (play button) does not prevent direct media access.

**Why it matters**  
- Media can be:
  - downloaded
  - scraped
  - embedded externally
- No control over:
  - access
  - playback
  - rate
- Breaks future assumptions about:
  - user-based playback
  - monetization
  - licensing

**Current behavior**  
- UI:
  - playback gated via auth modal
- Backend:
  - no access control on `/uploads`
- Result:
  - media is effectively public

**Future solution**  
- Signed URLs (short-lived)
- Authenticated stream proxy endpoint
- CDN-based token validation

**Priority:** HIGH (for controlled-access model)

**When to address:** Before introducing monetization, licensing constraints, or private content tiers

---

## Release grid image performance (no responsive optimization)

**Description**  
Release grids (studio + public artist page) render large numbers of cover images using plain `<img>` tags.

Current behavior:
- `loading="lazy"` only applied in compact mode
- no responsive sizing (`srcset`)
- no image optimization pipeline

**Why it matters**  
- Over-fetching large images on mobile
- Increased bandwidth usage
- Slower scrolling on large catalogs (100–200+ releases)
- Potential layout shifts

**Current behavior**  
- Full-size images served
- Browser handles loading heuristics
- No explicit optimization layer

**Future solution**  
- Generate image derivatives (thumbnails)
- Add responsive image support (`srcset`)
- Optionally migrate to Next.js `<Image>` with proper loader config
- Ensure consistent lazy loading across all grids

**Priority:** MEDIUM

**When to address:** When catalog sizes grow or mobile performance becomes relevant

