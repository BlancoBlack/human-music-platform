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
