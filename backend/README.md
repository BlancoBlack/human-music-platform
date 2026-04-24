# Backend (FastAPI)

## Python Version Requirement

This project requires **Python 3.10 or higher**.

It will NOT run on Python 3.9 or lower due to usage of modern typing syntax (e.g. `str | None`).

Check your version:

```bash
python3 --version
```

Project-wide quickstart (Redis, venv, API, worker, frontend) lives in the **[root README.md](../README.md)**. Work from this directory for Python commands.

---

## Backend Architecture (Authoritative)

### Current runtime behavior

- Database URL resolution lives in `app/core/database.py`:
  - if `DATABASE_URL` is set, it is used directly
  - otherwise default is SQLite at `backend/dev.db`
- Schema authority is Alembic (`alembic/`, `alembic.ini`, `alembic/versions/*`).
- Startup behavior in `app/main.py`:
  - in `APP_ENV=dev|development`: attempts automatic `alembic upgrade head`
  - always asserts DB revision is current (`_assert_schema_is_current`) unless `SKIP_SCHEMA_CHECK=1`
  - enforces treasury invariant via `ensure_treasury_entities`
- `Base.metadata.create_all()` exists only behind `ALLOW_SCHEMA_BOOTSTRAP=true` and is an escape hatch for isolated local bootstrap/testing.

### Architecture decisions

- **Schema:** Alembic is the only authoritative schema system for normal runtime and CI.
- **Startup mutation policy:**
  - allowed: treasury invariant enforcement (`ensure_treasury_entities`)
  - forbidden in normal mode: schema creation/mutation
  - bootstrap compatibility mode (`ALLOW_SCHEMA_BOOTSTRAP=true`) is legacy-only and not part of the default workflow
- **Seeds:** `seed_core_state.py` is the only official developer seed; `seed_genres.py` is CI/internal minimal taxonomy seed.
- **CI:** minimal and deterministic (migrate + taxonomy seed + tests).

---

## Database

- Default local DB file: `backend/dev.db`.
- Override with `DATABASE_URL` (SQLite/Postgres URL supported by SQLAlchemy engine config).
- `APP_BASE_DIR` can be set when deriving the default local DB path in non-standard execution contexts.
- Legacy references to `test.db` remain in some helper scripts/manual SQL docs and are not the default backend runtime target.

---

## Schema Management and Alembic

### Normal flow (official)

1. Run migrations: `.venv/bin/python -m alembic upgrade head`
2. Start API: `.venv/bin/python -m uvicorn app.main:app --reload --host localhost --port 8000`

### What startup does

- In dev environments, startup may auto-run migrations to head.
- Startup still enforces schema revision consistency and fails fast when stale.
- Startup does not create schema in normal mode.

### Bootstrap escape hatch (legacy)

- `ALLOW_SCHEMA_BOOTSTRAP=true` enables `Base.metadata.create_all()` and compatibility patches.
- This is for isolated recovery/bootstrap only, not standard development or production operation.

---

## Seeds and Data Initialization

### Official developer seed

- **Core seed (only official developer seed):**
  - `PYTHONPATH=. .venv/bin/python scripts/seed_core_state.py`
  - deterministic/idempotent core dataset; internally runs genre seed, ensures treasury, seeds users/artists/songs, simulates listening, and generates V2 payout artifacts
  - use `--reset` only when intentionally wiping domain data

### CI/internal minimal seed

- **Taxonomy-only seed (CI and internal use only):**
  - `PYTHONPATH=. .venv/bin/python scripts/seed_genres.py`

### Optional / scoped seeds

- `scripts/seed_data_v2.py`:
  - treated as legacy optional seed path
  - default mode resets a large portion of domain data
  - `--no-reset` can be unsafe because `_upsert_songs` matches globally by title

- `app/seeding/seed_discovery_realistic_v2.py`:
  - discovery QA/scale dataset only
  - not part of default developer bootstrap

- `scripts/bootstrap_local_db.sh`:
  - non-standard legacy helper
  - uses `test.db` and can diverge from default `dev.db` runtime flow

---

## CI Database and Seed Flow

`.github/workflows/ci.yml` backend job currently runs:

1. `rm -f dev.db`
2. `python -m alembic upgrade head`
3. `PYTHONPATH=. python scripts/seed_genres.py`
4. `python -m pytest`

This CI flow is intentionally minimal (schema + taxonomy + tests), not full demo-data seeding.

---

## Developer Setup (canonical)

### Setup

From `backend/`:

0. Prerequisite: Python `3.10+` (3.9 is not supported by current runtime annotations).
1. Create virtual environment:
   - `python3.11 -m venv .venv`
2. Activate:
   - `source .venv/bin/activate`
3. Upgrade pip:
   - `pip install --upgrade pip`
4. Install all runtime + test dependencies:
   - `pip install -r requirements.txt`
5. Run migrations:
   - `python -m alembic upgrade head`
6. (Optional local data) seed core state:
   - `PYTHONPATH=. python scripts/seed_core_state.py`
7. Run API:
   - `uvicorn app.main:app --reload`
   - If port 8000 is busy: `uvicorn app.main:app --reload --port 8001`

For worker:

- `.venv/bin/python worker.py`

### Testing

All test dependencies are included in `requirements.txt` (not a separate dev file currently).

From `backend/`:

- Run full suite: `.venv/bin/python -m pytest`
- Run a specific file: `.venv/bin/python -m pytest tests/test_auth.py`

---

## Seed Tutorial — Full App Data (Songs, Covers, Discovery)

Use this tutorial when you want a fully populated local app with:

- multiple artists and songs
- song metadata and credits
- listening history and payout artifacts
- discovery-ready catalog data
- working media URLs (audio + cover) for playback/UI testing

This flow uses one reusable audio file and one reusable cover image for seeded songs.

### What this tutorial includes

- `scripts/seed_core_state.py` as the official full developer seed
- optional discovery-scale dataset (`app/seeding/seed_discovery_realistic_v2.py`)
- explicit local media asset setup required by these seed paths

### Step 0 — Prerequisites

From `backend/`:

```bash
.venv/bin/python -m alembic upgrade head
```

### Step 1 — Create required folders

From repository root:

```bash
mkdir -p backend/uploads/songs
mkdir -p backend/uploads/covers
```

### Step 2 — Add required seed media files

Place these exact files:

- `backend/uploads/songs/seed_master.wav`
- `backend/uploads/covers/seed_cover.png`

Format requirements (strict):

- `seed_master.wav`:
  - WAV format
  - 24-bit
  - 44.1 kHz sample rate
- `seed_cover.png`:
  - PNG format
  - 3000x3000 resolution

Notes:

- These files are not committed to Git.
- They are intentionally reused across seeded songs for deterministic local bootstrap.

### Step 3 — Run the full developer seed

From `backend/`:

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_core_state.py
```

Optional clean rebuild:

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_core_state.py --reset
```

What this seed does:

- ensures treasury entities
- seeds taxonomy (`seed_genres` internally)
- seeds users, artists, songs, credits, splits, media rows
- simulates listening events
- builds V2 payout snapshot/lines

### Step 4 — Optional discovery-scale seed (QA load shape)

From `backend/`:

```bash
PYTHONPATH=. .venv/bin/python -m app.seeding.seed_discovery_realistic_v2
```

Use this only for discovery QA/scale tests; it is not the default dev bootstrap.

### Step 5 — Run API and verify media behavior

Start API:

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host localhost --port 8000
```

Quick checks:

- open `http://localhost:8000/docs`
- call discovery and catalog routes (for example `/discovery/home`, `/artists/{id}/songs`)
- verify returned `audio_url` / `cover_url` paths load without 404

### Important behavior if files are missing

- Seed scripts still complete (they write DB media paths/rows).
- Playback, processing, or downstream services may fail or behave incorrectly.
- App responses may include media URLs that return 404.
- UI can appear partially broken (missing covers/audio playback) without a seed-time crash.

For reliable local DX, always place the two required files before running full seeds.

---

## Related Paths

| Path | Role |
|------|------|
| `app/core/database.py` | Engine config, default `dev.db`, env URL override |
| `app/main.py` | Startup migration/assertion behavior and treasury invariant |
| `alembic/` + `alembic.ini` | Schema migration source of truth |
| `app/seeding/seed_common.py` | Shared seed helpers and schema guard (`ensure_schema`) |
| `scripts/seed_core_state.py` | Only official developer seed |
| `scripts/seed_genres.py` | CI/internal minimal taxonomy seed |
| `scripts/seed_data_v2.py` | Legacy optional seed |
| `app/seeding/seed_discovery_realistic_v2.py` | QA/scale discovery seed |
| `scripts/bootstrap_local_db.sh` | Legacy/non-standard `test.db` bootstrap helper |
| `alembic.ini` / `alembic/` | Schema revisions (step 1 above) |

---

## Authorization and Ownership Model

Authorization combines JWT identity, RBAC permissions, and ownership checks.

- **Auth identity:** Bearer JWT (`get_current_user`).
- **RBAC permissions:** `require_permission(...)` with permission checks from `has_permission(...)`.
- **Ownership data:** `artists.owner_user_id` (FK to `users.id`) for resource-level checks.

Current important endpoint protections:

- `POST /artists/{artist_id}/songs`:
  - requires RBAC permission `upload_music`
  - requires ownership-aware access via `can_edit_artist`
- Admin payout/settlement routes:
  - require RBAC permission `admin_full_access`
  - also use impersonation guard on sensitive mutations

`assert_user_owns_song` (in `song_lifecycle_service.py`) remains in use for song mutation routes that validate ownership via song -> artist linkage.

### Admin bootstrap (dev)

To create/admin-enable a user in local development, assign an admin role in `user_roles`:

```sql
INSERT INTO user_roles (user_id, role)
VALUES (<USER_ID>, 'admin');
```

Or update an existing user role row:

```sql
UPDATE user_roles
SET role = 'admin'
WHERE user_id = <USER_ID>;
```

Testing flow:
- login (or register) and obtain access JWT
- call admin endpoints with `Authorization: Bearer <token>`

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
