# Backend — current implementation

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
- Release grid behavior:
  - published releases only,
  - top 5 limit,
  - recency ordering by `CASE ... COALESCE(discoverable_at, created_at)`.
- Track list behavior:
  - ready + published-linked tracks,
  - cover derived from release cover map,
  - no canonical dependency on song-level cover rows.

### Slugs and public routes

- Public slug routes implemented:
  - `GET /artist/{slug}`,
  - `GET /album/{slug}`,
  - `GET /track/{slug}`.
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
