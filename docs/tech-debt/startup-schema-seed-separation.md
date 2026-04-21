# Tech debt: Startup / schema / seed separation

**Status:** MOSTLY RESOLVED (historical record retained)  
**Priority (remaining work):** LOW

---

## Historical context (resolved direction)

Current FastAPI startup (`startup_init` in `app/main.py`) performs:

- Schema validation (`_assert_schema_is_current`)
- Dev auto-migration (`_attempt_dev_auto_migration`)
- Business invariant safety logic (`ensure_treasury_entities`)

This previously bundled **three concerns** into one lifecycle hook:

1. **Application startup**
2. **Database migration / schema shape**
3. **Presence of seeded business data** (genres, treasury artist, etc.)

This created hidden coupling. Example that already affected CI:

- The global SQLAlchemy engine points at `dev.db` (or `DATABASE_URL`).
- Startup runs **before** request-scoped `get_db` overrides in tests.
- If the file is empty or only partially migrated, startup can execute logic that assumes schema exists.

Current mitigation is now part of the official architecture: CI explicitly runs `alembic upgrade head` and `scripts/seed_genres.py` before `pytest` (see `.github/workflows/ci.yml`).

---

## Current state vs original debt

Resolved or intentionally accepted:

1. **Schema authority resolved:** Alembic is the official schema system for runtime and CI.
2. **Seed role clarified:** developer core seed is `scripts/seed_core_state.py`; CI/internal minimal seed is `scripts/seed_genres.py`.
3. **Startup schema mutation removed in normal mode:** `create_all` is restricted to explicit bootstrap mode (`ALLOW_SCHEMA_BOOTSTRAP=true`).
4. **Treasury startup behavior is intentional:** startup safety net remains by design, while core seed also ensures treasury entities.

Remaining tradeoff:

- Startup still mutates treasury rows as a deliberate invariant safety net (not a generic seed mechanism).

---

## Target architecture (adopted)

Three explicit layers are now adopted.

### 1. Schema bootstrap (mandatory)

- Owned by **Alembic** (and CI/CD / operator steps).
- Runs **before** the app process is expected to serve traffic (or before tests that spin the full app).
- Guarantees **tables and columns only**.
- **No** assumption that business seed data exists.

### 2. Business data bootstrap (optional / controlled)

- **Explicit** seed scripts (`scripts/seed_core_state.py` for developer bootstrap, `scripts/seed_genres.py` for CI/internal minimal taxonomy).
- **Idempotent** (safe to re-run).
- Executed:
  - in **CI** when a suite needs canonical data;
  - in **dev** manually or via a documented script / compose step;
  - in **staging/prod** via migration-adjacent jobs or release automation as appropriate.
- **Never** implicitly required for “app can start” unless product explicitly defines that (then document and gate with flags).

### 3. Application startup (pure runtime)

- Must **not** depend on:
  - specific rows existing (treasury artist, genre catalog, etc.), or
  - seed scripts having run.
- Should be **safe on an empty but migrated** database regarding schema.
- Treasury invariant enforcement at startup is intentionally retained as a narrow safety net.

---

## Remaining follow-ups (small)

- Keep startup treasury enforcement narrow and documented as intentional safety behavior.
- Continue reducing legacy `test.db` references in old helper docs/scripts to avoid workflow confusion.

---

## Accepted architecture snapshot

- Schema: Alembic-first and enforced.
- Startup: no schema mutation in normal mode; treasury safety net retained.
- Developer seed: `scripts/seed_core_state.py`.
- CI seed: `scripts/seed_genres.py` minimal taxonomy only.

---

## Related

- [infra.md](./infra.md) — CI, workers, migration runbooks.
- [backend.md](./backend.md) — API and schema evolution context.

*Added: 2026-04-14. Updated: 2026-04-21 to mark resolution and preserve historical context.*
