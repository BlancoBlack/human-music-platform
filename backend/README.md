# Backend (FastAPI)

Project-wide quickstart (Redis, venv, API, worker, frontend) lives in the **[root README.md](../README.md)**. Work from this directory for Python commands.

---

## Database Architecture (IMPORTANT)

### Source of truth

**Alembic migrations** are the only schema authority at runtime.  
**SQLAlchemy models** define desired ORM shape, but startup no longer auto-creates/mutates schema.

### How schema gets applied

| Layer | What it does |
|--------|----------------|
| **Alembic** (`alembic/`, `alembic.ini`) | **Required** path for schema changes and upgrades. Run `alembic upgrade head` before app startup. |
| **`app/main.py` startup (`startup_init`)** | Verifies DB revision is current and fails fast if outdated. |
| **`Base.metadata.create_all()`** | Disabled in normal runtime; allowed only with explicit `ALLOW_SCHEMA_BOOTSTRAP=true` for isolated local bootstrap/testing. |
| **`ensure_schema()`** in `app/seeding/seed_common.py` | Enforces Alembic revision by default; optional bootstrap mode only via explicit env flag. |
| **`migrations/*.sql`** | **Legacy / manual** SQL for brownfield SQLite DBs (constraints, FK rebuilds, payout hardening). **Not** run automatically on app start. See `migrations/README.md` for when and how to apply them. |

### Mental model

> **If you want to change schema → add an Alembic migration.**  
> App startup and seed tooling now fail fast when DB schema is stale.

### DO NOT

- **Do not** skip `alembic upgrade head` before running app/seeds.
- **Do not** delete `migrations/*.sql` (or skip reading `migrations/README.md`) without understanding upgrades for **existing** dev/prod SQLite databases.
- **Do not** rely on implicit schema creation in production paths.

---

## Related paths

| Path | Role |
|------|------|
| `app/core/database.py` | Engine, `Base`, `SessionLocal` |
| `app/seeding/seed_common.py` | `ensure_schema()`, `reset_existing_data()`, shared seed helpers |
| `scripts/seed_data_v2.py` | Default V2 seed + ledger |
| `app/seeding/seed_discovery_realistic_v2.py` | Large discovery-focused seed |
| `alembic.ini` / `alembic/` | Bootstrap revision only (see above) |

---

## Song Ownership Model

Artist-level ownership is enforced via `artists.user_id` (FK to `users.id`).

Mutating song endpoints require the authenticated user to own the artist linked to the song:

| Endpoint | Auth | Ownership check |
|----------|------|-----------------|
| `POST /songs` | `get_current_user` | `artist.user_id == current_user.id` |
| `PATCH /songs/{id}` | `get_current_user` | `assert_user_owns_song` |
| `DELETE /songs/{id}` | `get_current_user` | `assert_user_owns_song` |
| `PUT /songs/{id}/splits` | `get_current_user` | `assert_user_owns_song` |

`assert_user_owns_song` (in `song_lifecycle_service.py`) loads the song (excluding soft-deleted rows), resolves `song.artist_id -> artist.user_id`, and compares against the caller.

**Known gap:** `upload-audio` and `upload-cover` endpoints do not enforce authentication or ownership yet.

---

## Soft Delete (songs)

Songs use **soft delete** via `songs.deleted_at` (nullable `DateTime`).

- `DELETE /songs/{id}` sets `deleted_at = now()` instead of removing the row.
- All product-facing queries filter `Song.deleted_at.is_(None)`: catalog, discovery, streaming, listening sessions, analytics (user-facing metrics).
- **Payout / financial queries must NOT filter** `deleted_at` — deleted songs may still have outstanding payouts.
- Migration: `0012_song_soft_delete_deleted_at` (Alembic).

---

## Release Scheduling (MVP)

Scheduled releases use release lifecycle state + discovery timestamp:

- `publish_release()` sets:
  - `state="scheduled"` when `release_date > now`
  - `discoverable_at = release_date`
- Auto-publish transitions:
  - `scheduled -> published` when `now >= discoverable_at`
  - implemented by `publish_due_releases(db)` in `app/services/release_service.py`

Current infrastructure is intentionally simple:

- polling loop runs inside `worker.py`
- each interval performs DB query/update for due scheduled releases
- no external cron or distributed scheduler in MVP

Config:

- `RELEASE_AUTO_PUBLISH_INTERVAL_SECONDS` (default: `45`)

Notes:

- This replaces the previous temporary behavior where discovery compensated for
  scheduled visibility.
- Discovery should now rely on published releases (`state="published"`) and
  `discoverable_at` time gating.

---

## Discovery System Overview

Current discovery (`GET /discovery/home`) is a **single pipeline**:

1. candidate generation (`build_candidate_set`)
2. multi-score ranking (`score_candidates`)
3. ranking constraints (`finalize_discovery_ranking`)
4. structured/adaptive section selection (`compose_discovery_sections`)
5. hydration + strict normalization (`build_discovery_home_sections`)

### Section intent (V1 implemented)

| Section | Intent | Notes |
|---|---|---|
| `play_now` | Fast, low-friction starting point | weighted top-5 entry pick + variety; strict artist cap |
| `for_you` | Personalized with exploration budget | adaptive high/mid/low bucket mixing |
| `explore` | Fair-discovery lane | excludes top popularity tail and enforces quality guardrails |
| `curated` | Human/editorial lane | static allowlist for now; still de-duplicated/capped |

### Discovery mechanics currently in code

- Anti-viral popularity normalization: `log(1 + popularity)` in scoring.
- Artist diversity:
  - global ranked set: max 2 tracks/artist
  - `play_now`: max 1 track/artist
  - other sections: max 2 tracks/artist
- Structured + adaptive selection:
  - soft buckets (`high`/`mid`/`low`) per section score
  - deterministic pattern pool for `for_you`
  - constrained low-bucket injection for `explore`
- Direction/context layer:
  - per-track `context_tag` (`Fresh this week` / `Trending now` / `Hidden gem`)
  - optional top-level `section_microcopy`

## Discovery API Contract (`/discovery/home`)

Response keys:

- `play_now`, `for_you`, `explore`, `curated`: arrays of tracks
- `section_microcopy` *(optional)*: `Record<string, string>`

Per-track fields:

- `id: number`
- `title: string`
- `artist_name: string`
- `audio_url: string | null`
- `cover_url: string | null`
- `playable: boolean`
- `context_tag: string | null` *(optional)*

### Frontend behavior (current)

`frontend/app/discovery/page.tsx`:

- renders four sections in fixed order
- shows section microcopy when present
- shows `context_tag` under artist name when present
- applies subtle visual emphasis to the lead `play_now` item
- remains safe when optional fields are missing
