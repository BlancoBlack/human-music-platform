# Backend (FastAPI)

Project-wide quickstart (Redis, venv, API, worker, frontend) lives in the **[root README.md](../README.md)**. Work from this directory for Python commands.

---

## Database Architecture (IMPORTANT)

### Source of truth

**SQLAlchemy models** under `app/models/` (imported via `app/core/database.py` into `Base.metadata`) are the **only** authoritative definition of tables and columns. If the schema should change, **edit the models** first.

### How schema gets applied

| Layer | What it does |
|--------|----------------|
| **`Base.metadata.create_all()`** | Primary mechanism: creates missing tables/columns from models (`checkfirst` where used). |
| **`app/main.py` startup (`startup_init`)** | Runs `create_all` **plus required SQLite-only patches** (`_ensure_listening_session_hybrid_schema`, listening event columns/indexes, payout settlement columns, treasury `system_key` indexes, etc.). These exist so older SQLite files and incremental dev DBs stay compatible. |
| **`ensure_schema()`** in `app/seeding/seed_common.py` | Used by **seed scripts** and parity tooling: `create_all` plus `ensure_song_credit_entries_position_column`, auth/refresh token schema helpers, and `_ensure_sqlite_compat_columns()`. It **mirrors much of the startup intent** for processes that do not boot the full FastAPI app. |
| **Alembic** (`alembic/`, `alembic.ini`) | **Bootstrap tool only** today: revision `0001_bootstrap_schema` runs `Base.metadata.create_all(..., checkfirst=True)` so `alembic upgrade head` can initialize an empty SQLite file (e.g. CI or `scripts/bootstrap_local_db.sh`). It is **not** a full replacement for startup/seed compat logic. |
| **`migrations/*.sql`** | **Legacy / manual** SQL for brownfield SQLite DBs (constraints, FK rebuilds, payout hardening). **Not** run automatically on app start. See `migrations/README.md` for when and how to apply them. |

### Mental model

> **If you want to change schema → edit models.**  
> Everything else (`create_all`, startup patches, seeds, Alembic bootstrap) **adapts** to reflect or patch those models for local SQLite and tooling—it does not replace them as the source of truth.

### DO NOT

- **Do not** assume Alembic is the migration authority or that `alembic upgrade head` alone equals everything `main.py` startup does.
- **Do not** delete `migrations/*.sql` (or skip reading `migrations/README.md`) without understanding upgrades for **existing** dev/prod SQLite databases.
- **Do not** remove `create_all()` / startup `ensure_*` logic **without** a designed replacement (e.g. a full Alembic revision chain and a policy for when compat SQL runs).

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
