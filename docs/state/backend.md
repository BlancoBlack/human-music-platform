## LAST STABLE CHECKPOINT

- Commit message: feat(discovery): hardened analytics + antifraud + exploration v2 + frontend interaction + state alignment
- Status: stable
- Ready for: STATE LOCK

# Backend — current implementation

## AUDIT SNAPSHOT (2026-04-29) — Studio, Analytics, Payouts, Roles

### AUTH SYSTEM

- Auth routes are mounted under `/auth` in `backend/app/main.py` via `app.include_router(auth_router, prefix="/auth", tags=["auth"])`.
- `POST /auth/login` exists in `backend/app/api/auth_routes.py` and returns JSON `TokenResponse` with:
  - `access_token` (JWT bearer),
  - `refresh_token` (JSON-returned for tests/non-browser clients),
  - `token_type` (`bearer`).
- Login also sets an httpOnly cookie `hm_refresh_token` (path `/auth`) via `attach_refresh_cookie(...)` in `backend/app/api/auth_cookies.py`.
- Access-token auth is enforced by `get_current_user` in `backend/app/api/deps.py`, which accepts only `Authorization: Bearer <access_jwt>` using FastAPI `HTTPBearer(auto_error=False)`.
- Refresh flow (`POST /auth/refresh`) accepts refresh token from JSON or cookie; browser path is cookie-first (documented in code comments in `auth_routes.py` and frontend auth modules).
- Access JWT claims are validated in `backend/app/core/jwt_tokens.py` (`decode_access_token`):
  - requires `exp`, `iat`, `sub`,
  - enforces `typ=access` or `typ=access_impersonation`.

### ADMIN ACCESS

- There is no `is_admin` field on `User` (`backend/app/models/user.py`).
- Admin is role-based through `user_roles` (`backend/app/models/user_role.py`) and checked by `require_admin_user` in `backend/app/api/deps.py`.
- `require_admin_user` requires:
  - authenticated user from `get_current_user` (Bearer JWT required),
  - `admin` role exists in `roles`,
  - a `user_roles` row where `user_id=<current_user>` and `role='admin'`.
- Seeded admin user is configured in `backend/app/seeding/seed_system/users.py`:
  - email `borja@hellosamples.com`,
  - password `69476947`,
  - admin role assignment via `assign_role_to_user(..., role_name="admin")`.
- Admin payout routes (`/admin/payouts`, settle/retry endpoints, action-log endpoint) use `Depends(require_admin_user)` in `backend/app/api/routes.py`.

### ADMIN PAYOUTS API

- UPDATED (ENRICHED RESPONSE)
- `GET /admin/payouts` now mirrors the same enriched ledger grouping source as `/admin/payouts-ui`:
  - uses `fetch_admin_ledger_groups(...)`,
  - supports filter parity: `status`, `artist_id`, `artist_name`, `limit`.
- `artist_name` filter is resolved to artist IDs using the same lookup pattern as HTML UI (`LOWER(artists.name) LIKE %...%`), then passed as `artist_ids_from_name`.
- Response now includes enriched UI-facing fields:
  - `batch_id`,
  - `distinct_users`,
  - `artist_id`,
  - `artist_name`,
  - `amount` (cents to float),
  - `ui_status`,
  - `wallet`,
  - `tx` (`tx_id`, `explorer_url`),
  - `created` (from `created_at` fallback `period_end_at`),
  - `attempts`,
  - `failure_reason`.
- Backward-compat aliases are still returned for existing consumers (`status`, `created_at`, `attempt_count`, `destination_wallet`, `algorand_tx_id`, `tx_id`).
- Each row includes `batch_status` from `payout_batches.status` (for admin UI lock/polling).

### PROCESSING LOCK

- IMPLEMENTED
- `payout_batches.status` may be `processing`, `failed`, or `paid` (Alembic `0036_payout_batch_status_lock`, model check constraint updated).
- `process_batch_settlement(...)` and `retry_failed_settlements_for_batch(...)` move the batch to `processing` before on-chain work, then set `paid` / `failed` / `posted` from settlement rows (`_derive_payout_batch_status`).
- See **DB LOCKING** for cross-process safety when taking that transition.

### DB LOCKING

- IMPLEMENTED
- Runtime dialect comes from SQLAlchemy `engine.dialect.name` on the live engine in `app/core/database.py` (`DATABASE_URL` → PostgreSQL; unset → SQLite `backend/dev.db`).
- `app/services/payout_batch_lock.py`:
  - **PostgreSQL:** `PayoutBatch` row loaded with `.with_for_update()`, status re-checked, then `processing` in the same short transaction (commit releases the row lock; `processing` blocks concurrent callers).
  - **SQLite:** atomic `UPDATE payout_batches SET status='processing' WHERE id=? AND status IN (...)` (settle) or `status='failed'` (retry); exactly one session succeeds (`rowcount == 1`); concurrent losers raise `BatchLockContentionError` → **`POST /admin/settle-batch`** / **`POST /admin/retry-batch`** respond with **409** and detail `Batch is currently being processed by another admin`.
  - **PostgreSQL:** if the row is already `processing` after `FOR UPDATE`, same `BatchLockContentionError` / **409**.

### UX HARDENING

- IMPLEMENTED
- Lock contention is exposed as **HTTP 409** with a stable user-facing `detail` string (not a generic 500).
- `BatchLockContentionError` is defined in `app/services/payout_batch_lock.py` and caught in `post_admin_settle_batch` / `post_admin_retry_batch` in `backend/app/api/routes.py`.

### RETRY RESULT SUMMARY

- IMPLEMENTED
- `POST /admin/retry-batch/{batch_id}` returns JSON `{ "retried": int, "success": int, "failed": int }` (`success` = confirmed outcomes).
- `retry_batch` audit rows store the same three fields in `metadata` (no extra keys).

### ADMIN ACTION LOGGING

- IMPLEMENTED
- New DB-backed audit table/model exists: `admin_action_logs` (`backend/app/models/admin_action_log.py`, Alembic `0035_admin_action_logs`).
- `process_batch_settlement(...)` now accepts `admin_user_id` and writes an audit row after successful settle execution:
  - `action_type="settle_batch"`,
  - `target_id=<batch_id>`,
  - `admin_user_id=<current_admin_id>`,
  - `metadata` stores the settle result summary.
- New API endpoint `GET /admin/action-logs` is available, protected by `require_admin_user`, returning latest logs with limit.

### ADMIN LOGS (ENRICHED)

- IMPLEMENTED
- `GET /admin/action-logs` joins `users` and returns `admin_user_email` (nullable if missing), plus full `metadata` (including retry `retried` / `success` / `failed` and settle outcome counts).

### RETRY SYSTEM

- IMPLEMENTED
- New endpoint `POST /admin/retry-batch/{batch_id}` retries only failed settlement rows (`payout_settlements.execution_status='failed'`) for the batch.
- Retry path does not run full-batch orchestration and reuses existing per-artist settlement execution logic.
- Guardrails:
  - requires `payout_batches.status == 'failed'` (not merely a failed row on another batch status),
  - rejects when `payout_batches.status == 'processing'`,
  - rejects when the batch has no failed settlements to retry.
- Audit log is written on retry execution with `action_type="retry_batch"` and `target_id=<batch_id>` (see **RETRY RESULT SUMMARY** for `metadata` shape).

### ADMIN PAYOUTS UI

- LEGACY REMOVED
- Backend route/handler `GET /admin/payouts-ui` has been deleted from `backend/app/api/routes.py`.
- Admin payouts frontend now consumes JSON APIs only (`/admin/payouts`, `/admin/action-logs`).

## CURRENTLY IMPLEMENTED

### Documentation system behavior

- Documentation system enforces state-linked structure.
- All docs require explicit link to state files.
- Inconsistencies between docs and state are tracked in KNOWN ISSUES.

- Studio JSON endpoints are live and power the React `/studio` surfaces:
  - `GET /studio/me`,
  - `GET /studio/{artist_id}/dashboard`,
  - `GET /studio/{artist_id}/payouts`,
  - `GET /studio/{artist_id}/catalog`,
  - `GET /studio/{artist_id}/releases`,
  - approvals endpoints under `/studio/releases/*`.
- `GET /studio/{artist_id}/payouts` is implemented as a thin read-only adapter in `backend/app/api/routes.py`:
  - auth: `Depends(require_artist_owner)`,
  - source of truth: `app/services/payout_aggregation_service.py` only,
  - endpoint calls only:
    - `get_artist_payout_summary(...)`,
    - `get_artist_payout_history(...)`,
    - `get_artist_payout_capabilities(...)`,
  - no endpoint-local payout SQL / ledger-table query logic.
- `/studio/{artist_id}/payouts` response contract:
  - `summary`: `paid_eur`, `accrued_eur`, `pending_eur`, `failed_eur`, `batch_count`, `last_batch_date`,
  - `history[]`: `batch_id` (string), `date` (ISO string), `amount_eur`, `status` (`paid|pending|failed`), `users`, `tx_id` (nullable string from `payout_settlements.algorand_tx_id`, same value as admin payouts for the batch), `explorer_url` (nullable string: Lora transaction URL when `tx_id` is present, built in backend via `app/core/explorer_urls.py`, same logic as `GET /admin/payouts` `tx.explorer_url`),
  - `payout_method`: `selected` (`crypto|bank|none`), `supports_onchain_settlement`, `requires_manual_settlement`, `wallet_address`, `bank_configured`.
- On-chain transaction explorer links for API consumers are centralized in `app/core/explorer_urls.py` (`lora_transaction_explorer_url`), driven by `NETWORK` (`testnet` vs `mainnet`); studio payout history and admin payouts JSON both use this helper so URLs do not drift.
- Security posture for `/studio/{artist_id}/payouts` payout method payload:
  - does not expose bank detail text,
  - returns only `bank_configured` boolean for bank info presence.
- Artist payout configuration update is ownership-controlled:
  - `POST /artist/{artist_id}/payout-method` now uses `Depends(require_artist_owner)` (not admin-only),
  - validates `payout_method in {crypto, bank, none}`,
  - requires wallet when `crypto`, requires bank payload when `bank`,
  - response is JSON `{ success: true, payout_method: { selected, wallet_address, bank_configured } }` without exposing bank detail content.
- Legacy HTML dashboards remain active in `backend/app/api/routes.py`:
  - `/artist-analytics/{artist_id}`,
  - `/artist-dashboard/{artist_id}`,
  - `/dashboard/{user_id}`.
- `GET /artist-payouts/{artist_id}` is a **302 redirect** to Next Studio `/studio/payouts` (same `NEXT_APP_BASE_URL` as other hub links); the old HTML payouts page was removed. Payout data and method updates use `GET /studio/{artist_id}/payouts` and `POST /artist/{artist_id}/payout-method`.
- Artist analytics APIs are implemented in `analytics_service.py` and include:
  - streams over time,
  - top songs,
  - top fans,
  - narrative insights.
- Studio/artist dashboard totals are ledger-backed through `get_artist_dashboard()` and canonical aggregation in `app/services/payout_aggregation_service.py`.
- Canonical artist payout helpers now live in `payout_aggregation_service.py`:
  - `get_artist_payout_summary(...)`,
  - `get_artist_payout_history(...)`,
  - `get_artist_payout_capabilities(...)`.
- Bucket definitions are unified in that service:
  - paid = settlement `execution_status='confirmed'`,
  - failed = settlement `execution_status='failed'`,
  - pending = batch `status='calculating'`,
  - accrued = batch `status IN ('finalized','posted')` and settlement not confirmed/failed.
- Ownership-gated access is implemented via dependencies:
  - `require_artist_owner`,
  - `require_self_or_admin`,
  - context validators for studio context switching.

## PARTIALLY IMPLEMENTED

- Dual-surface model (legacy HTML + new JSON/studio) is still in operation; duplication risk remains across analytics/payout presentation paths.
- Frontend role-level UX expectations are ahead of backend route consolidation; enforcement is correct in key finance routes but product paths are not fully unified.

## NOT IMPLEMENTED

- No single consolidated creator backend surface has replaced all legacy dashboard handlers yet.
- No dedicated backend API specifically for `/studio/analytics` or `/studio/payouts` page contracts (those pages are placeholders in frontend).

## KNOWN ISSUES

- `GET /discovery/admin/analytics` in `backend/app/api/discovery_routes.py` appears exposed without explicit auth/admin dependency checks.
- Coexistence of legacy and modern dashboard endpoints increases maintenance and behavioral drift risk.

## ⚠️ SYSTEM INCONSISTENCIES

- Current creator product center is `/studio`, but backend still serves legacy dashboard HTML routes with overlapping business outputs.
- Analytics has both operational metrics APIs and estimated earnings helpers in the same service module, which can blur "insight" vs "economic truth" semantics.

## CURRENTLY IMPLEMENTED

### Core architecture

- FastAPI app with modular routers in `backend/app/main.py` and `backend/app/api/routes.py`.
- SQLAlchemy ORM with Alembic migrations as schema source of truth.
- SQLite-first runtime hardening:
  - migration preflight checks,
  - safe SQLite batch migration helper,
  - FK warning/verification checks during startup/runtime.

### Ownership and authorization model

- **Artist ownership source of truth is `artists.owner_user_id`**.
- Legacy `artists.user_id` has been removed from runtime ownership logic and dropped by migration `0022`.
- Write access is enforced through centralized dependencies in `backend/app/api/deps.py`:
  - `require_artist_owner`,
  - `require_song_owner`,
  - `require_release_owner`,
  - `enforce_artist_ownership`.
- Admin override is permission-based (`admin_full_access` / `edit_any_artist`) for artist-scoped guards.

### Studio context system

- Studio context is implemented and persisted on user rows:
  - `GET /studio/me` returns user, allowed artist/label contexts, and resolved `current_context`.
  - `POST /studio/context` validates and persists context (`user | artist | label`).
- Context resolution is fail-safe:
  - invalid/stale stored context is rejected,
  - fallback defaults to `{ type: "user", id: user.id }`.

### Upload system and release lifecycle

- Canonical upload path is release-aware:
  - `POST /songs` (draft song metadata),
  - `POST /songs/{song_id}/upload-audio`,
  - `PUT /songs/{song_id}/splits`,
  - cover upload via `POST /releases/{release_id}/upload-cover`.
- Single songs are release-linked via `create_single_release_for_song(...)`.
- Release publish endpoint is active: `POST /studio/releases/{release_id}/publish`.
- Release lifecycle states are enforced:
  - `draft -> published` (immediate),
  - `draft -> scheduled` (future release date),
  - scheduled auto-transition to published through worker polling (`publish_due_releases`).
- Publish validation enforces:
  - release-song artist consistency,
  - song state readiness,
  - cardinality rules (`single == 1 track`, `album >= 2 tracks`),
  - album release-cover requirement,
  - release approval gate (`approval_status == ready`).

### Cover model (release-owned)

- Cover ownership is release-only for active runtime behavior.
- Song cover constant has been removed from song media model:
  - `SongMediaAsset.kind` is constrained to `MASTER_AUDIO` only.
- Effective cover resolution is release-based:
  - `effective_song_cover(...)` resolves from `ReleaseMediaAsset`,
  - returns `None` for songs without release linkage.
- Song cover write path is deprecated/disabled:
  - `POST /songs/{song_id}/upload-cover` returns `410 Gone`,
  - service-level `upload_song_cover_art(...)` raises deprecation error.
- Release cover upload (`upload_release_cover_art`) recomputes upload status for **all linked songs**.

### Splits and invariants

- Canonical split writes go through `set_splits_for_song(...)`.
- Invariants are enforced centrally:
  - one row per artist,
  - valid shares,
  - deterministic `split_bps` allocation summing exactly `10000`,
  - versioning on rewrite (`song_artist_splits.version`).
- Split changes propagate to release approval state via `releases.split_version` and participant sync.

### Approval system

- Release participant model is active (`release_participants`):
  - participant roles: `primary | collaborator | featured`,
  - approval metadata: `requires_approval`, `approval_type`, `status`, `approved_at`,
  - rejection metadata: `rejection_reason`.
- Release-level approval source is `releases.approval_status` (`draft | pending_approvals | ready`).
- Split-version invalidation is active:
  - accepted split participants are reset to pending when `approved_split_version != releases.split_version`.
- Approval APIs are active:
  - `GET /studio/pending-approvals`,
  - `GET /studio/releases/{release_id}`,
  - `POST /studio/releases/{release_id}/approve`,
  - `POST /studio/releases/{release_id}/reject`.

### Catalog and recency behavior

- Studio catalog endpoint: `GET /studio/{artist_id}/catalog`.
  - Hero `releases[]` (top 5): **`first_track`** is resolved via shared **`_get_first_tracks_for_releases`** — one `ROW_NUMBER() OVER (PARTITION BY release_id …)` query plus batched **`SongMediaAsset`** (master audio). The legacy **per-release** `Song` query + `.first()` **N+1 pattern is removed**; behavior is **aligned** with `GET /studio/{artist_id}/releases`.
  - For hero `releases[]` and **`first_track`**, **cover** is **strictly release-owned** (`ReleaseMediaAsset` → `release_cover_map` → public URL). **`effective_song_cover` is not used** for those payloads; if the release has no cover asset, `cover_url` / `first_track.cover_url` are **null** (no song-level cover fallback).
- Studio releases list (full grid): `GET /studio/{artist_id}/releases`.
  - Same `require_artist_owner` gate as catalog.
  - Returns `{ "releases": [...] }` where each item matches the catalog `releases[]` row shape (`id`, `slug`, `title`, `type`, `release_date`, `cover_url`, `first_track`).
  - All **published** releases for the artist, no limit; ordering matches the catalog hero grid: `CASE ... COALESCE(discoverable_at, created_at) DESC`.
  - Uses the same **`_get_first_tracks_for_releases`** batched first-track resolution and the same **release-only** cover rules for release rows and **`first_track`** as catalog hero (no `effective_song_cover` on those objects).
- Release grid behavior:
  - published releases only,
  - top 5 limit,
  - recency ordering by `CASE ... COALESCE(discoverable_at, created_at)`,
  - each release includes `first_track` (first `upload_status=ready` song in album order: `track_number` then `id`) with the same playback-shaped fields as catalog track rows, or `null` if none.
- Track list behavior:
  - ready + published-linked tracks,
  - cover resolution is strictly release-owned (`track_release_cover_map` -> `public_media_url_from_stored_path`) with `null` when no release cover exists,
  - does not call `effective_song_cover` and does not depend on song-level cover rows.
- All catalog-related cover resolution is now strictly release-owned. Song-level cover is no longer used anywhere in catalog runtime payloads.

### Discovery telemetry and analytics (hardened)

- Discovery home endpoint `GET /discovery/home` now returns additive `request_id` (UUID per response payload).
- Impression telemetry is backend-authored (not frontend-emitted): after section composition/finalization, one `discovery_events` row is inserted per surfaced track in final section order (`play_now`, `for_you`, `explore`, `curated`) with:
  - `event_type="impression"`,
  - `request_id`,
  - optional `user_id`,
  - `song_id`, `artist_id` (always set from ranking/song metadata path), `section`, `position`,
  - additive metadata: `metadata_json.ranking_version="v1"` and `metadata_json.section_position_global` (cross-section absolute index using render order `play_now -> for_you -> explore -> curated`),
  - score snapshot in `metadata_json.scores` (`play_now`, `for_you`, `explore`) unchanged,
  - additive normalized score mirrors for analytics stability: `metadata_json.score_play_now`, `metadata_json.score_for_you`, `metadata_json.score_explore` (duplicates of `scores` values; legacy `scores` retained unchanged),
  - additive provenance/debug keys: `metadata_json.candidate_pool` (`popular | user | low_exposure | curated | unknown`) and `metadata_json.explore_excluded` (boolean, when present in ranking row; defaults false).
- Impression volume control is env-configurable via `DISCOVERY_IMPRESSION_SAMPLE_RATE` (clamped `0.0..1.0`, default `1.0` = previous no-loss behavior). Sampling is request-level (single decision per `request_id`): either all impressions for that request are inserted or none; ranking/section composition behavior is unchanged.
- Dev startup now logs effective discovery sampling config (`DISCOVERY_IMPRESSION_SAMPLE_RATE` parsed value + raw env) to reduce "no data" ambiguity in telemetry debugging.
- Play telemetry ingestion endpoint is active: `POST /discovery/events`.
  - Current accepted event type: `play_click`.
  - Backend enriches with optional authenticated `user_id` and `artist_id` lookup from `song_id`, writes to `discovery_events`, and stores additive metadata key `metadata_json.ranking_version` (`"v1"` default; frontend may send explicitly).
  - Dev-only insert confirmation logs are emitted for impression/play_click writes to aid pipeline validation (`request_id`, inserted count / song_id, allowed flag) without changing payload contracts.
- Discovery-to-listening correlation is active via additive session linkage:
  - `POST /stream/start-session` accepts optional additive fields `discovery_request_id`, `discovery_section`, `discovery_position`,
  - `listening_sessions.discovery_request_id` (nullable) stores request-level origin when playback starts from discovery,
  - existing listening validation/payout flow remains unchanged (`ListeningEvent` contract untouched).
- Internal discovery analytics aggregation endpoint is active: `GET /discovery/admin/analytics` (read-only, no schema changes). It returns pre-aggregated blocks for:
  - CTR by section,
  - CTR by global position (chart-ready rows),
  - candidate pool performance,
  - candidate pool by section (`section`, `candidate_pool`, `impressions`, `clicks`, `ctr`, `share`),
  - CTR by ranking version (`metadata_json.ranking_version`),
  - top artists concentration (`top_artists`, `top_artists_share`, `total_impressions`),
  - high-score/low-CTR anomaly candidates,
  - diversity-per-request summary (`avg_unique_artists`, `min_unique_artists`, `max_unique_artists`),
  - score-bucket CTR correlation (`score_ctr_correlation`) for ranking drift detection.
  All metrics are computed directly from `discovery_events` (+ existing JSON metadata keys) without introducing new infrastructure or background pipelines.
- Admin analytics aggregates are hard-windowed to the last 24 hours (`created_at >= datetime('now', '-1 day')`) for freshness/stability and to avoid mixing old ranking regimes into active operational views.
- CTR/impression robustness: analytics counts use distinct impression keys (`request_id || '-' || song_id`) instead of raw row counts, preventing duplicate-row inflation and preserving request-level comparability.
- Analytics safety guard: if `discovery_events` is missing (misaligned DB), `GET /discovery/admin/analytics` returns empty additive blocks instead of crashing the route.
- Dev-only health probe endpoint exists: `GET /discovery/debug/telemetry-check` returns lightweight telemetry status (`has_discovery_events_table`, `total_rows`, `impressions_last_1h`, `clicks_last_1h`); hidden outside dev by returning `404`.
- Startup migration reliability in development: app startup checks current Alembic revision vs head and runs non-destructive `upgrade head` automatically when behind, logging current revision(s), target, and result.
- New telemetry storage table: `discovery_events` (migration `0032_discovery_events_table`):
  - indexed columns for queryable dimensions (`event_type`, `created_at`, `request_id`, `song_id`, `user_id`),
  - flexible payload in `metadata_json` for forward-compatible extensions.

### Alembic idempotency fix (CI stability)

- Migrations `0032_discovery_events_table`, `0033_listening_session_discovery_request_id`, and `0034_add_discovery_context_to_listening_sessions` are now idempotent.
- This is required because `0001_bootstrap` uses `Base.metadata.create_all()`, which can pre-create newer tables/columns on fresh databases before later revisions execute.
- `0032` now checks table/index existence before create/drop operations; `0033` and `0034` now check column existence before add/drop operations.
- Prevents duplicate table/column errors in fresh CI DB bootstrap flows (for example: `discovery_events already exists`).
- No schema redesign, no data migration, and no runtime behavior/API change.
- Classified as a stability fix, not a feature change.

### Discovery quality metrics (session-level)

- Discovery-to-listening linkage uses canonical keys: `discovery_events(request_id, song_id)` -> `listening_sessions(discovery_request_id, song_id)` -> `listening_events(session_id)`.
- `listening_sessions` includes additive discovery-origin fields:
  - `discovery_request_id` (nullable),
  - `discovery_section` (nullable),
  - `discovery_position` (nullable).
- `POST /stream/start-session` accepts additive optional fields `discovery_request_id`, `discovery_section`, `discovery_position` and persists them on session creation when provided; existing start-session flow remains valid without these fields.
- Session quality in current system is derived (no new events/tables):
  - click -> session rate (discovery click produced session),
  - session -> valid listen rate (session has `listening_events.is_valid=1`),
  - average session duration (`listening_sessions.total_duration`, discovery-origin sessions),
  - early drop rate (`total_duration < 10` seconds, fixed threshold).
- Discovery admin analytics endpoint (`GET /discovery/admin/analytics`) now returns additive quality blocks:
  - `quality_by_section`,
  - `quality_by_candidate_pool`,
  - `quality_by_score_bucket`.
- Discovery quality metrics v2 (listen-per-impression) are active as additive blocks on the same endpoint:
  - `listen_per_impression_by_section`,
  - `listen_per_impression_by_candidate_pool`,
  - `listen_per_impression_by_score_bucket`.
  Definition: `listen_per_impression = valid_listens / impressions` where impressions are deduped by `(request_id, song_id)` and valid listens are linked via `listening_sessions -> listening_events(is_valid=1)`.
- KPI interpretation:
  - `CTR` measures click propensity (interaction),
  - `valid_listen_rate` measures post-click quality,
  - `listen_per_impression` is the primary discovery outcome KPI (true conversion from served track to validated listening),
  - `session_rate` is mainly a reliability/bridge metric (click -> session creation success), not a discovery quality KPI by itself.
- Listening economic source of truth is unchanged: validation and payout semantics still come from `listening_events` / stream ingestion; discovery quality metrics only read existing records.
- Current limitations:
  - no explicit skip event,
  - no viewport/truth-of-visibility in these quality metrics,
  - session duration quality depends on existing session finalization behavior (`total_duration` lifecycle), and can under-represent active/unfinalized sessions,
  - `ended_at` exists on `listening_sessions` as lifecycle metadata, but duration logic is intentionally unchanged in this phase.

### Antifraud integration with discovery (implemented + analysis)

- Current antifraud model (implemented):
  - Inputs: `raw_duration`, song duration metadata, prior **valid** listens by `(user_id, song_id)` from `listening_events`, and server time.
  - Rules (`validate_listen`):
    - duration gate: valid when `real_duration >= max(30s, 30% of song duration)` (`30s` fallback when song duration missing),
    - spacing gate: invalid if prior valid listen for same `(user, song)` occurred < 2h ago,
    - daily cap gate: max 5 valid listens per `(user, song)` per UTC day,
    - repeat decay (for valid listens): `weight = exp(-0.22 * repeats_last_24h)`.
  - Outputs: `is_valid`, `validated_duration`, `weight`, `validation_reason` stored on `listening_events`.
- Economic linkage (implemented):
  - Snapshot/payout flows consume only antifraud-qualified listens (`listening_events.is_valid = true`) and `validated_duration`/`weight`.
  - Worker aggregates (`ListeningAggregate`, `GlobalListeningAggregate`) are updated from valid events only, so discovery popularity/relevance inputs are already antifraud-filtered indirectly.
- Discovery mapping (current state):
  - Ranking/candidate generation:
    - popular/user pools use `GlobalListeningAggregate` / `ListeningAggregate` -> implicitly antifraud-aware,
    - ranking also applies an explicit antifraud-aware quality penalty (v3) using existing aggregate-derived signals (`quality_score` from `rel_raw`/`pop_raw`) as a bounded multiplicative adjustment.
  - Telemetry:
    - impressions/clicks are behavioral telemetry (`discovery_events`) and are not antifraud-validated signals.
  - Quality analytics:
    - session/valid-listen outcomes join via `discovery_request_id` and `listening_events.is_valid`, so outcome metrics are antifraud-aware.
- Gaps identified:
  - Medium: ranking penalty still uses an aggregate proxy (`quality_score` from `rel_raw`/`pop_raw`) rather than direct outcome KPI optimization (`listen_per_impression`, `valid_listen_per_click`).
  - High: impression/click diagnostic metrics (CTR, click-rate blocks) can still look strong for shallow/fraud-prone patterns if interpreted without antifraud outcome KPIs.
  - Medium: candidate pool construction does not yet use direct per-song antifraud outcome floors (beyond current quality penalty + exposure controls).
  - Medium: session-duration-derived metrics remain weaker antifraud proxies than `is_valid` outcomes (active session / finalize timing caveats).
- Proposed integration points (no implementation yet):
  - Ranking V1: add antifraud-aware reweighting term derived from historical `valid_listen_per_impression` / `valid_listen_per_click` by song (bounded penalty, not hard filter).
  - Candidate generation V1: tag/downrank tracks with sustained low antifraud outcome conversion instead of excluding by default.
  - Analytics V1 split:
    - truth metrics: `listen_per_impression`, `valid_listen_per_click`, valid-listen outcomes by section/pool/score bucket,
    - diagnostic metrics: CTR, raw click/session rates, section-position click curves.
  - Session/click handling V1: keep existing `(request_id, song_id)` dedupe + section-safe click joins; no extra event types required.
- Prioritized roadmap:
  - Implement first: antifraud-aware ranking reweight + pool-level quality floor using existing derived metrics (low complexity, high impact, no infra).
  - Delay: skip/dwell micro-events, viewport truth instrumentation, dynamic anomaly models.
  - Overkill now: new event buses, new telemetry tables, external stream processors.

### Discovery ranking antifraud penalty (v3)

- Previous issue:
  - v2 still showed mid-range collapse at the penalty floor, so low and medium quality rows were often not differentiated.
- Updated formula (same quality input, refined curve):
  - `quality_score = (valid_listens + 1) / (impressions + 5)` (implemented from existing ranking inputs: `rel_raw`, `pop_raw`),
  - `penalty = clamp(0.4 + 0.6 * quality_score, 0.55, 1.0)`,
  - `final_score = base_score * penalty`.
- Behavior intent:
  - low quality -> bounded downrank (floor-protected),
  - medium quality -> partial recovery so ranking resolution is restored,
  - high quality -> minimal penalty / clearer reward.
- Constraint and stability:
  - uses existing aggregates only (no additional request-time queries),
  - no schema/API/telemetry changes,
  - preserves candidate pools and ranking structure,
  - improves ranking resolution without introducing instability.

### Discovery exploration pressure (v1, superseded)

- Current issue:
  - discovery impressions were over-indexed on `candidate_pool="popular"` because candidate-universe merge/cap behavior and pool labeling made low-exposure representation effectively disappear in practice.
- Fix at that stage (additive):
  - candidate-universe construction now reserves a minimum low-exposure slice before normal merge/fill (`popular -> user -> low_exposure`) so long-tail candidates survive the global cap,
  - section composition attempted a per-response low-exposure floor across algorithmic sections (`play_now`, `for_you`, `explore`) using bounded tail replacement from already-ranked low-exposure candidates.
- Rationale:
  - make fairness and exploration hypotheses testable in production telemetry,
  - ensure antifraud and quality metrics can be evaluated on non-popular inventory, not only head content.
- Constraints:
  - additive and non-breaking,
  - no schema/API/infra changes,
  - no new telemetry event types,
  - no new query classes (reuses existing candidate pool queries and in-memory ranked rows).

### Discovery exploration pressure (v2)

- v1 issue:
  - low-exposure candidates entered the universe, but section-level exposure stayed materially below target in served rows (observed single-digit share).
- Root cause:
  - v1 enforcement depended mainly on low-exposure tracks already surviving ranked selection; when that set was thin after ranking/caps, replacement inventory was insufficient.
- Fix:
  - low-exposure enforcement is now the **final mutation stage** in `compose_discovery_sections` (after section limits, dedupe, and artist-cap-driven selection),
  - strict per-section target: `required = ceil(section_size * 0.25)`,
  - if below target, replace tail (lowest-priority) non-low-exposure rows with highest-ranked low-exposure rows,
  - enforcement now uses an **external low-exposure reservoir** captured pre-ranking (`low_exposure` pool before section filtering), so injection does not depend only on final ranked survivors,
  - fallback allows low-exposure reuse across sections to preserve minimum share when unique inventory is limited.
- Guarantee:
  - each served algorithmic section (`play_now`, `for_you`, `explore`) enforces the minimum low-exposure target via final-stage replacement and external reservoir fallback (including reuse fallback when unique inventory is constrained).
- Tradeoff:
  - slight ranking-purity loss is accepted in exchange for reliable fairness/discovery exposure constraints.
- Debug visibility:
  - dev-only structured logs emitted per section:
    - `low_exposure_enforcement.section`,
    - `required`,
    - `before`,
    - `after`,
    - `target` (same value as `required`),
    - `added_from_reservoir`.
- Rationale:
  - make fairness/discovery behavior testable in production telemetry rather than aspirational, including long-tail inventory not naturally favored by head-focused ranking.

### Discovery tech debt (v1)

- Detailed tech-debt record is tracked in `docs/tech-debt/discovery_v1_limitations.md`.
- Current status: discovery is stable/functional with antifraud-aware ranking inputs, antifraud-aware outcome analytics, and enforced low-exposure pressure.
- Improvements are intentionally deferred (not blockers) until higher production data confidence is available.
- Current focus remains product usability, real user data collection, and validating system behavior before adaptive optimization/experimentation layers.

#### Discovery analytics hardening (dedupe + time window)

- Deduplication rule for outcome linkage is canonical `(request_id, song_id)`:
  - impressions are deduped by `COUNT(DISTINCT request_id || '-' || song_id)`,
  - valid listens are deduped via `valid_pairs` (`SELECT DISTINCT ls.discovery_request_id AS request_id, ls.song_id` from `listening_sessions` joined to `listening_events` where `is_valid=1`).
- Time-window rule for funnel consistency:
  - only impressions are strictly window-filtered (`de.event_type='impression' AND created_at >= datetime('now','-1 day')`),
  - clicks are also window-filtered to the same 24h range for section-level attribution consistency,
  - `listening_sessions` / `listening_events` are joined without strict 24h cutoff to avoid dropping late-arriving post-impression outcomes.
- Section-safe click attribution is enforced where section is part of the metric grain: click joins use `(request_id, song_id, section)` matching (`COALESCE(clk.section,'') = COALESCE(imp.section,'')`) to prevent cross-section leakage.
- Additive KPI block on `GET /discovery/admin/analytics`:
  - `valid_listen_per_click_by_section` with `clicks`, `valid_listens`, `valid_listen_per_click`.
- Metric interpretation:
  - `session_rate` is primarily a bridge/reliability metric (click -> session creation),
  - `valid_listen_per_click` measures post-click quality,
  - `listen_per_impression` remains the primary end-to-end discovery quality KPI.

### Slugs and public routes

- Public slug routes implemented:
  - `GET /artist/{slug}`,
  - `GET /artist/{slug}/releases`,
  - `GET /artist/{slug}/tracks`,
  - `GET /album/{slug}`,
  - `GET /track/{slug}`.
- `GET /artist/{slug}/releases` is public (no auth), returns published releases only, and matches studio release-card payload fields (`id`, `slug`, `title`, `type`, `release_date`, `cover_url`, `first_track`); `first_track` uses shared batched resolution (`_get_first_tracks_for_releases`) and release-owned cover URLs only.
- `GET /artist/{slug}/tracks` is public (no auth), defaults to `sort=top`, and returns track rows filtered to `upload_status=ready` joined to **published** releases only; payload shape mirrors catalog track rows (`id`, `slug`, `title`, `artist_name`, `duration_seconds`, `release_date`, `stream_count`, `cover_url`, `audio_url`, `playable`) with release-only cover resolution (no song-level fallback).
- Canonical slug redirect behavior (301) is active for historical/non-canonical slugs.
- Slug history tables are active for artist/release/song resolution continuity.

### Seeds and migrations

- Modular seeding system exists under `backend/app/seeding/seed_system/`.
- Release-centric media seeding is active (release cover + song master audio).
- Migration utilities/scripts for SQLite safety are present:
  - `backend/scripts/dev_migrate.py`,
  - `backend/scripts/test_full_migration.py`.
- Cover migration utility exists:
  - `backend/scripts/backfill_release_cover_from_song_cover.py` (historical data backfill).

## PARTIALLY IMPLEMENTED

- Legacy ingestion endpoint `POST /artists/{artist_id}/songs` still exists for compatibility and is marked deprecated.
- Legacy/no-release song visibility fallback still exists in `is_song_discoverable(...)` (`upload_status == ready` for `release_id IS NULL`) as backward-compat behavior.
- RBAC normalization to strict FK linkage (`user_roles.role_id`) is not complete; string role linkage is still in use.
- Scheduler is polling-based (single-process style) and not yet a distributed scheduler.

## REMOVED / DEPRECATED BEHAVIOR

- Song-level cover as an active write model is removed.
- `SONG_MEDIA_KIND_COVER_ART` is removed from runtime model constraints.
- `POST /songs/{song_id}/upload-cover` is intentionally deprecated (`410`).
- Upload cover fallback logic is no longer part of canonical backend behavior.

## KNOWN GAPS / OPERATIONAL RISKS

- In-memory stream rate limiting is process-local (not shared/distributed).
- Non-SQLite ingestion locking parity is deferred (Postgres path lacks equivalent lock strategy).
- Some legacy docs/messages may still mention old song-cover upload order and need continuous cleanup.
- Seed execution still has unrelated data-integrity edge cases in some scripts/environments (e.g. duplicate system keys, invalid split sums in legacy data paths).
