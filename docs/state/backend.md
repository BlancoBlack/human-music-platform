# Backend — current implementation

## CURRENTLY IMPLEMENTED

### Application shell

- **FastAPI** app in `backend/app/main.py`: title “Human Music Platform API”, OpenAPI tags (Streaming, Payouts, Analytics, Dev Tools, Onboarding).
- **CORS**: `CORSMiddleware` with `allow_credentials=True`; origins from `CORS_ORIGINS` (comma-separated), always includes `http://localhost:3000`.
- **Static uploads**: `GET` files under `/uploads` (directory `uploads/` relative to process cwd).
- **Routers**:
  - `auth_router` → prefix `/auth`
  - `discovery_router` → prefix `/discovery`
  - main `router` from `app.api.routes` (no global prefix in `main.py`)

### Database

- **SQLAlchemy** engine + `SessionLocal` in `app/core/database.py`.
- **Default**: if `DATABASE_URL` is unset, uses **SQLite** file `backend/dev.db` (path derived from repo layout).
- **Override**: set `DATABASE_URL` for other engines (e.g. PostgreSQL). Same codebase path; some behaviors are dialect-specific (see [streaming.md](./streaming.md) for ingestion locking).
- **Schema**: production path expects **Alembic** at head (`_assert_schema_is_current` on startup unless `SKIP_SCHEMA_CHECK=1` or `ALLOW_SCHEMA_BOOTSTRAP=true`). In `APP_ENV`/`ENV` = `dev`/`development`, startup runs `alembic upgrade head` automatically.
- **Dependency reproducibility**: `backend/requirements.txt` now declares direct runtime/test dependencies needed for API startup, Alembic migrations, and pytest execution in a clean venv install (Python `3.10+` runtime target), including explicit `bcrypt` pinning compatible with passlib hashing behavior.
- **SQLite startup patches** (when dialect is sqlite): optional columns/triggers for listening sessions, listening event idempotency/correlation, payout settlement columns, treasury indexes — see `main.py` helpers.

### Endpoints (grouped by domain)

**Health / meta**

- `GET /api` — JSON `{"message": "Human Music Platform API"}`

**Onboarding**

- `GET /tutorial` — HTML tutorial page

**Streaming** (`routes.py`, tags include Streaming)

- `POST /stream` — production listen ingestion (Bearer or legacy header; see [auth.md](./auth.md))
- `POST /stream/start-session` — create `ListeningSession` bound to a song
- `POST /stream/checkpoint` — append `ListeningSessionCheckpoint` (non-economic)

**Dev-only streaming** (gated by `require_dev_mode()` — allowed when `APP_ENV`/`ENV` ∈ `{dev, development, local, test}` **or** `ENABLE_DEV_ENDPOINTS=true`)

- Internal + public variants of `POST /dev/stream` (user id via query/form for testing)
- `GET /dev/events` — inspect recent `ListeningEvent` rows

**Economics previews** (no ledger write from these alone)

- `GET /payout/{user_id}` — user-centric preview: `calculate_user_distribution` + `expand_song_distribution_to_artists`; returns songs + artists in cents; meta `currency: EUR`, `mode: user-centric-preview`
- `GET /pool-distribution` — `calculate_global_distribution()`
- `GET /compare/{user_id}` — `compare_models(user_id)` (user vs global pool, excludes system songs)

**Discovery**

- `GET /discovery/home` — ranked sections + hydrated tracks (see [discovery.md](./discovery.md))
- `POST /discovery/first-session` — onboarding-first playback trigger returning `{ tracks, mode: "onboarding" }` with diversity/emerging-leaning track selection from discovery pipeline.
- `POST /onboarding/preferences` — saves onboarding taste inputs (`genres` max 5, optional `artists`) to `user_profiles`.
- `POST /onboarding/complete` — marks onboarding completion (`users.onboarding_completed=true`, `users.onboarding_step="COMPLETED"`).
- **Onboarding state transitions are validated and reentrant**: backend keeps strict ordered states (`REGISTERED` -> `PREFERENCES_SET` -> `DISCOVERY_STARTED` -> `COMPLETED`) while onboarding endpoints are idempotent for same-or-ahead states, enabling safe retries/resume without transition errors.

**Catalog / artists / releases / uploads** (representative)

- Songs: `POST /songs`, `GET|PATCH|DELETE /songs/{song_id}`, `POST /songs/{song_id}/upload-audio`, `POST /songs/{song_id}/upload-cover`, `PUT /songs/{song_id}/splits`
- Releases: `POST /releases`, `GET /releases/{release_id}/tracks`, `POST /releases/{release_id}/upload-cover`
- Genres: `GET /genres`, `GET /genres/{genre_id}/subgenres`
- Artists: `GET /artists/search`, `GET /artists/{artist_id}`, `GET /artists/{artist_id}/songs`, `POST /artists/{artist_id}/songs` (multipart: title, optional `release_id`, audio `file`)
- Permission + ownership guard active: `POST /artists/{artist_id}/songs` requires RBAC permission `upload_music` and passes ownership-aware access (`can_edit_artist`).

**HTML “artist hub” pages** (server-rendered HTML in `routes.py`)

- `GET /dashboard/{user_id}` — legacy comparison HTML (uses `compare_models`)
- `GET /artist-dashboard/{artist_id}` — earnings + global comparison + insight fetch via client JS
- `GET /artist-analytics/{artist_id}` — charts / analytics HTML
- `GET /artist-payouts/{artist_id}` — payout ledger UI HTML
- `GET /admin/payouts-ui` — admin ledger HTML

**Analytics JSON** (public artist guard via `_get_public_artist_or_404`)

- `GET /artist/{artist_id}/streams`
- `GET /artist/{artist_id}/top-songs`
- `GET /artist/{artist_id}/top-fans`
- `GET /artist/{artist_id}/insights`

**Admin / settlement** (RBAC permission gate active via `admin_full_access`; several routes also use `require_non_impersonation`)

- `GET /admin/payouts`
- `POST /admin/settle-batch/{batch_id}`
- `POST /admin/retry-payout/{payout_id}`
- Permission guard active: admin ledger/settlement routes require RBAC permission `admin_full_access`.

**Artist payout method (MVP, RBAC-protected)**

- `POST /artist/{artist_id}/payout-method` — form fields; requires `admin_full_access`

**Auth** — see [auth.md](./auth.md) (`/auth/*`).

### Background jobs (RQ)

- **Redis** client and default **Queue** `"default"` in `app/core/queue.py` (`localhost:6379`).
- **Worker entry**: `backend/worker.py` runs `SpawnWorker` on that queue.
- **Enqueued job**: `process_listening_event` from `app/workers/listen_worker.py` after each successful `ListeningEvent` commit in `StreamService`.
- **Settlement**: `process_batch_settlement` imported in `routes.py` (from `settlement_worker`); invoked from admin/batch flows (see [economics.md](./economics.md)).

### Services / modules (high-level map)

- **Streaming**: `stream_service`, `listening_validation`, `listening_checkpoint_service`; `listening_integrity_service` — **internal only** (module docstring: not wired to API routes; rebuild/reconciliation helpers).
- **Economics preview**: `payout_service`, `pool_payout_service`, `artist_distribution_service`, `comparison_service`, `royalty_split`, `song_split_distribution`
- **Ledger UI / V2**: `snapshot_service`, `payout_v2_snapshot_engine`, `payout_ledger_ui_service`, `settlement_breakdown`, `settlement_worker`, `global_model_v2_service`
- **Analytics**: `analytics_service`, `artist_dashboard_service`
- **Discovery**: `discovery_candidate_pools`, `discovery_ranking`, `discovery_hydration`
- **Upload / catalog**: `song_ingestion_service`, `song_media_upload_service`, `song_metadata_service`, `song_lifecycle_service`, `release_service`, etc.
- **RBAC support**: `rbac_service` validates role existence for assignments, aggregates permissions across all user roles, and logs warnings when legacy `user_roles.role` values do not map to `roles.name`.
- **Artist access support**: `artist_access_service` provides ownership-aware checks (`can_edit_artist`) that combine permissions with `Artist.owner_user_id`, `create_artist_for_user` sets `owner_user_id` to the current user at creation time, `get_user_owned_artists(user_id, db)` returns owned artist rows for backend reuse, and `can_upload_song(user, artist, db)` prepares onboarding-aware upload caps (not yet enforced by routes).

### ORM models (tables imported via `app/core/database.py`)

- Auth: `user`, `user_profile`, `user_role`, `refresh_token`
- RBAC: `role`, `permission`, `role_permission` (permissions assigned to role names referenced by `user_roles.role`)
- Catalog: `song`, `song_featured_artist`, `song_credit_entry`, `song_media_asset`, `release`, `release_media_asset`, `genre`, `subgenre`, `artist`, `label`, `song_artist_split`
- Listening: `listening_event`, `listening_session`, `listening_session_checkpoint`, `listening_aggregate`, `global_listening_aggregate`, `ingestion_lock`
- Money / subs: `user_balance`
- Payout V2: `payout_batch`, `payout_line`, `payout_input_snapshot`, `snapshot_user_pool`, `snapshot_listening_input`, `payout_settlement`

## PARTIALLY IMPLEMENTED

- **PostgreSQL parity for listen ingestion**: `stream_service` documents that **ingestion serialization** (`ingestion_locks`) is implemented for **SQLite** only; non-SQLite dialects log `ingestion_lock_skipped_unsupported_dialect` and do not acquire an equivalent lock.
- **Algorand client**: `algorand_client_v2.py` uses a **fixed** public algod URL (`testnet-api.algonode.cloud`); mainnet switching for the client itself is **not** evident in that file (network naming exists elsewhere for explorer URLs).
- **RBAC role linkage**: runtime role validation is implemented for assignment paths; schema remains string-driven for behavior compatibility, with transitional nullable `user_roles.role_id` FK added for future normalization.
- **Artist ownership backfill posture**: `artists.owner_user_id` exists with FK to `users.id`, currently nullable for compatibility with existing/system artist rows and seed/runtime bootstrap data.
- **Artist creation flow consistency**: ownership-aware creation helper exists, but not all creation entry points are unified under it yet (runtime/system bootstrap and seed paths still create `Artist` rows directly).
- **Role-based registration rollout**: `POST /auth/register` normalizes legacy/new payloads into canonical persisted role state (`role=user|artist`, optional `sub_role`). Legacy `role_type=label` is mapped to canonical `role=artist, sub_role=label`; RBAC assignment remains `artist` for creator accounts.
- **Onboarding state rollout**: `users.onboarding_completed` and `users.onboarding_step` are now used by auth/onboarding routes with strict transition checks; onboarding preferences persist in `user_profiles.preferred_genres` and `user_profiles.preferred_artists`.
- **Sub-role state**: `users.sub_role` stores artist-vs-label registration intent for role `artist` payloads while RBAC assignment remains final authority for permissions.
- **Permission enforcement rollout**: RBAC permission dependency (`require_permission`) is active on selected high-risk routes (artist upload + admin payout/settlement endpoints), not yet applied across all mutating endpoints.
- **Ownership enforcement rollout**: artist upload mutation now uses combined RBAC + ownership checks (`require_permission("upload_music")` and `can_edit_artist`), with admin permission paths bypassing ownership through the helper.
- **Admin authorization model**: admin endpoints are authorized through RBAC (`require_permission("admin_full_access")`) with JWT identity.

## NOT IMPLEMENTED

- **Dedicated “state” HTTP API** for clients: state is inferred from existing routes and services; there is no `/v1/system-state` style aggregate.
- **Separate `generate_payouts` symbol** as named in some informal docs: ledger line generation is **`generate_payout_lines`** in code (see [economics.md](./economics.md)).

## KNOWN ISSUES

- **Rate limits** on `/stream` and related endpoints use **in-memory** stores (`threading.Lock` + `deque`) — effective per **process** only, not cluster-wide.
- **`song_id` on `ListeningEvent`**: ORM column has **no `ForeignKey`** in `listening_event.py` (integrity relies on application logic and SQLite FK pragma for other tables).
- **Refresh rotation under SQLite**: `auth_routes` documents that without PostgreSQL `FOR UPDATE`, concurrent refresh can race.
