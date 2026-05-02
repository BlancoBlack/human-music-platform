# Human Music Platform

Event-driven Web3 music streaming platform.

## Stack

- Backend: FastAPI
- Frontend: Next.js
- Blockchain: Algorand
- Architecture: Event-driven

### Requirements

- Python **3.11+** (backend and tests; the codebase uses `datetime.UTC` and other 3.11+ APIs).
- Install dependencies: `pip install -r requirements.txt` from the **`backend/`** directory (see **Quickstart**).

## How it works

1. User triggers stream
2. Backend stores stream
3. Event is emitted
4. Worker processes event
5. Blockchain transaction executed

## Quickstart

**1. Infra (repo root)** — Redis for RQ:

```bash
docker compose -f infra/docker-compose.yml up -d
```

**2. Backend** — create venv and install deps (`backend/`):

```bash
cd backend
cp .env.example .env
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -r requirements.txt
```

Edit `backend/.env` as needed (see **Environment variables**).

**3. API** (`backend/`):

Use hostname **`localhost`** (not `127.0.0.1`) so the browser, cookies, and `NEXT_PUBLIC_API_BASE` all agree.

```bash
./.venv/bin/python -m alembic upgrade head
PYTHONPATH=. ./.venv/bin/python scripts/seed_core_state.py
./.venv/bin/python -m uvicorn app.main:app --reload --host localhost --port 8000
```

**4. Worker** (`backend/`, same shell conventions):

```bash
./.venv/bin/python worker.py
```

**5. Frontend** (`frontend/`):

Create `frontend/.env.local` (see `frontend/.env.example`):

```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

Open the app at **http://localhost:3000** (not `http://127.0.0.1:3000`) so refresh cookies and CORS line up with the API.

Then:

```bash
cd frontend
npm ci
npm run dev
```

On Windows, use `.venv\Scripts\python.exe` instead of `./.venv/bin/python`.

### Frontend setup

The Next.js app lives in **`frontend/`**. Install dependencies locally after cloning — the UI uses **[TanStack Query](https://tanstack.com/query)** (`@tanstack/react-query`) for likes (`GET /likes`, optimistic updates) and for loading playlists in the add-to-playlist modal (`GET /playlists`).

The frontend uses **[@dnd-kit](https://dndkit.com/)** (**`@dnd-kit/core`**, **`@dnd-kit/sortable`**, and **`@dnd-kit/utilities`**) for playlist track drag-and-drop reordering on **`/library/playlists/[id]`**. Those dependencies are declared in **`frontend/package.json`** and are installed automatically with **`npm install`** or **`npm ci`** — no additional setup.

After cloning, from the repo root:

```bash
cd frontend
npm install
npm run dev
```

Configure **`frontend/.env.local`** with `NEXT_PUBLIC_API_BASE=http://localhost:8000` (see **Quickstart** §5). Use **`localhost`** (not `127.0.0.1`) so cookies and CORS match the API.

For reproducible installs in CI or when the lockfile is your source of truth, prefer **`npm ci`** (as in **Quickstart** §5) instead of **`npm install`**.

### Running tests

Backend tests live under **`backend/tests/`**. Install backend dependencies from **`backend/requirements.txt`** before running **`pytest`**.

**`httpx`** is listed there explicitly: FastAPI’s **`TestClient`** (Starlette) depends on it, so HTTP integration tests such as **`test_playlist_http.py`** and **`test_playlist_playback_http.py`** import cleanly and are not skipped.

```bash
cd backend
pip install -r requirements.txt
pytest
```

Prefer the same **`backend/.venv`** interpreter as in **Quickstart** (e.g. `./.venv/bin/python -m pip install -r requirements.txt` then `./.venv/bin/python -m pytest`).

## Requisites

### 1. System requirements

**macOS / Linux / Windows (WSL recommended for shell parity)**  
General-purpose OS; no OS-specific code paths were detected in the repo.

**Docker Desktop or Docker Engine + Compose plugin**  
Runs Redis (and an unused Postgres service) from `infra/docker-compose.yml`.

Install: [Docker Desktop](https://docs.docker.com/desktop/) or [Docker Engine](https://docs.docker.com/engine/install/)

Example (from repo root): `docker compose -f infra/docker-compose.yml up -d`

**Redis reachable at `localhost:6379`**  
Required for RQ: stream events enqueue `process_listening_event`, and some API paths enqueue payout batch jobs.

Install via Docker (see above) or: [Redis download](https://redis.io/docs/latest/operate/oss_and_stack/install/install-redis/)

---

### 2. Python environment

**Python 3.11+**  
Use the same major.minor Python on every machine (e.g. MacBook and Mac Studio). The backend pins **3.11** in `backend/.python-version` (for pyenv/asdf); there is no repo-root `pyproject.toml` or `runtime.txt`.

Install: [python.org/downloads](https://www.python.org/downloads/) or `brew install python@3.11` / `python@3.12` (macOS)

#### Execution rule (backend)

All backend and worker commands assume:

1. **Current working directory is `backend/`** (the folder that contains `app/`, `worker.py`, and `requirements.txt`).
2. **Interpreter is always `backend/.venv`** — never the system Python, Homebrew `python3`, or a global `uvicorn` on `PATH`.

**Database & schema (single overview):** canonical backend architecture, Alembic workflow, startup behavior, and seed strategy — see **[backend/README.md — Backend Architecture](backend/README.md#backend-architecture-authoritative)**.

Create the environment once per machine (do not copy `.venv` between computers):

```bash
cd backend
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -r requirements.txt
```

Optional: `source .venv/bin/activate` for an interactive shell — still prefer **`./.venv/bin/python -m …`** for API and worker so the interpreter cannot drift.

**`python-dotenv`**  
`app/main.py`, `worker.py`, and `scripts/seed_data_v2.py` load `backend/.env` (or process environment). See `backend/.env.example` for all backend keys.

**Windows:** use `.venv\Scripts\python.exe` in place of `./.venv/bin/python`.

#### Password hashing (bcrypt compatibility)

This repo pins **`passlib[bcrypt]==1.7.4`** and **`bcrypt==4.0.1`**. Newer **`bcrypt` (≥4.1)** removes APIs that Passlib 1.7.4 expects, which surfaces at runtime as:

`AttributeError: module 'bcrypt' has no attribute '__about__'`

If your venv picked up a newer bcrypt, reinstall the pinned stack from `backend/`:

```bash
./.venv/bin/python -m pip uninstall bcrypt -y
./.venv/bin/python -m pip install "bcrypt==4.0.1" "passlib[bcrypt]==1.7.4"
```

Do **not** run `pip freeze > requirements.txt` unless you intend to refresh the whole dependency set deliberately.

---

### 3. Environment variables

Create **`backend/.env`** (or export variables in your shell). Example:

```env
# Required for on-chain payouts (legacy per-user payout worker) and V2 batch settlement.
ALGOD_MNEMONIC="abandon abandon abandon ... (25-word testnet-funded account)"

# Block explorer base (Lora). Values: testnet | mainnet. Does NOT change algod URL in code.
NETWORK="testnet"

# Optional: max rounds to wait for settlement tx confirmation (default 1000).
SETTLEMENT_TX_WAIT_ROUNDS="1000"

# Optional: after finalize, run settlement (default on). Use 0/false/no/off to disable.
AUTO_SETTLEMENT_AFTER_FINALIZE="1"

# Optional: run auto-settlement in a background thread vs same thread (default on).
AUTO_SETTLEMENT_ASYNC="1"

# Browser origins allowed for credentialed CORS (comma-separated). http://localhost:3000 is always merged in if missing.
CORS_ORIGINS="http://localhost:3000"

# --- Auth (see backend/.env.example for full list) ---
JWT_SECRET_KEY="your-super-secret-key-at-least-32-characters-long"
JWT_ALGORITHM=HS256
JWT_REFRESH_DAYS=30
APP_ENV=development
ENABLE_DEV_IMPERSONATION=true
ENABLE_LEGACY_AUTH=false
AUTH_COOKIE_SECURE=false
```

| Variable | Purpose | Example |
|----------|---------|---------|
| `ALGOD_MNEMONIC` | Signs Algorand payment/ASA transfers for payouts and V2 settlement. | 25-word mnemonic (testnet) |
| `NETWORK` | Chooses testnet vs mainnet **explorer** links in the API/UI only. | `testnet` |
| `SETTLEMENT_TX_WAIT_ROUNDS` | Passed to algod confirmation wait for settlements. | `1000` |
| `AUTO_SETTLEMENT_AFTER_FINALIZE` | After V2 batch finalize, trigger settlement unless disabled. | `1` or `0` |
| `AUTO_SETTLEMENT_ASYNC` | If enabled, settlement runs in a daemon thread after finalize. | `1` or `0` |
| `CORS_ORIGINS` | Comma-separated browser origins for credentialed CORS. Defaults include `http://localhost:3000` (always enforced if omitted from the list). | `http://localhost:3000` |
| `NEXT_APP_BASE_URL` | Next.js base URL for server-side links/redirects. | `http://localhost:3000` |

### Environment variables (Auth System)

`app/main.py` and `worker.py` call **`load_dotenv()`** so variables in **`backend/.env`** are available before routes import auth. If `JWT_SECRET_KEY` is missing or shorter than **32 characters**, token creation fails with a clear `RuntimeError`.

| Variable | Required | Purpose |
|----------|----------|---------|
| `JWT_SECRET_KEY` | **Yes** | Secret for signing access and refresh JWTs (minimum **32** characters). |
| `JWT_ALGORITHM` | No | Default `HS256`. |
| `JWT_REFRESH_DAYS` | No | Refresh token lifetime in days (default `30`). |
| `APP_ENV` / `ENV` | Recommended | e.g. `development` for local dev; used with `ENABLE_DEV_IMPERSONATION`. |
| `ENABLE_DEV_IMPERSONATION` | No | Must be **false or unset in production**. When true with dev `APP_ENV`, enables `POST /auth/dev/impersonate`. |
| `ENABLE_LEGACY_AUTH` | No | Default **`false`** (Bearer-only on listening). Deprecated: set `true` only temporarily for legacy clients that send `X-User-Id` without JWT — **not recommended for production**. |
| `CORS_ORIGINS` | No | Credentialed CORS allowlist; see `main.py`. |
| `AUTH_COOKIE_SECURE` | No | Set `true` when the API is served over HTTPS. |

**Session model:** **`GET /auth/me`** requires **`Authorization: Bearer <access_jwt>`** only. The **httpOnly refresh cookie** is for **`POST /auth/refresh`**, **`POST /auth/logout`**, and is set on **register/login** — it is **not** used as a second identity mechanism for `/auth/me`.

**Production:** rotate `JWT_SECRET_KEY` if exposed; never commit real `.env`; keep dev-only flags off.

**Note:** `app/blockchain/algorand_client_v2.py` uses a **hardcoded** Algod URL (`https://testnet-api.algonode.cloud`) and empty token. Changing `NETWORK` does not switch RPC endpoints; use that only for explorer URLs.

**Frontend (`frontend/.env.local`)**

| Variable | Purpose | Example |
|----------|---------|---------|
| `NEXT_PUBLIC_API_BASE` | FastAPI base URL for browser `fetch` calls | `http://localhost:8000` |

---

### 4. Database

**SQLite**  
Default local DB is **`backend/dev.db`** when `DATABASE_URL` is not set (configured in `app/core/database.py`).

**`DATABASE_URL` override**  
If `DATABASE_URL` is set, SQLAlchemy uses that value directly (SQLite/Postgres supported by driver config).

**Alembic**  
Schema authority is Alembic (`backend/alembic`, `backend/alembic.ini`). CI runs `python -m alembic upgrade head` before tests.

**Startup rules (`app/main.py`)**

- In `APP_ENV=dev|development`, startup attempts `alembic upgrade head`.
- Startup then validates DB revision is current (fails fast when stale, unless `SKIP_SCHEMA_CHECK=1`).
- `Base.metadata.create_all()` is only used in explicit bootstrap mode (`ALLOW_SCHEMA_BOOTSTRAP=true`), not normal runtime.

**Postgres in Docker**  
`infra/docker-compose.yml` defines Postgres, but the application code does not use it with the current `DATABASE_URL`.

---

### 5. Blockchain (Algorand)

**Algorand TestNet account**  
Fund the address derived from `ALGOD_MNEMONIC` with ALGO (and opt in / hold test USDC if exercising ASA payouts). [Algorand dispenser / docs](https://developer.algorand.org/docs/)

**`py-algorand-sdk`**  
Used for signing and submitting transactions (`algosdk`).

**USDC ASA**  
`app/workers/settlement_worker.py` uses asset id **10458941** (testnet USDC example in code). Wrong network or asset will fail on-chain.

---

### 6. Developer tools

**Node.js + npm**  
For the Next.js frontend (`frontend/package.json`: Next 16, React 19). Use a current LTS (e.g. 20.x or 22.x).

Install: [nodejs.org](https://nodejs.org/)

```bash
cd frontend && npm install
```

**Uvicorn**  
Run only via the backend venv: `./.venv/bin/python -m uvicorn app.main:app --reload` from `backend` (see **Run locally**). Do not run a global `uvicorn` binary.

**RQ worker**  
Use the **same** `backend/.venv` as the API: `./.venv/bin/python worker.py` from `backend` while Redis is up.

**Scripts (from `backend`, same `.venv` as API)**  

| Script | Role |
|--------|------|
| `PYTHONPATH=. ./.venv/bin/python scripts/seed_core_state.py` | Official core seed for local/dev demos |
| `PYTHONPATH=. ./.venv/bin/python scripts/seed_genres.py` | CI/internal minimal taxonomy seed |
| `./.venv/bin/python scripts/seed_data_v2.py` | Legacy optional seed path (use with care) |
| `./.venv/bin/python scripts/test_distribution_vs_ledger_parity.py` | Distribution vs ledger parity check |
| `./.venv/bin/python scripts/test_stream_concurrency.py` | Concurrent `/stream` smoke test (API must be running) |
| `./.venv/bin/python -m pytest tests/` | `backend/tests/` |

## Discovery (current)

- Endpoint: `GET /discovery/home`
- Pipeline: candidate generation → multi-score ranking → structured/adaptive selection → hydration/normalization.
- Sections: `play_now`, `for_you`, `explore`, `curated`.
- Per-track fields: `id`, `title`, `artist_name`, `audio_url`, `cover_url`, `playable`, optional `context_tag`.
- Optional top-level metadata: `section_microcopy`.

Frontend (`/discovery`) renders section microcopy and context tags when present, with safe fallback when optional fields are missing.

For detailed backend implementation notes and contract context, see [`backend/README.md`](backend/README.md).

**Cursor / VS Code extensions (inferred)**  

- **Python** — backend development  
- **Pylance** — typing and IntelliSense for Python  
- **ESLint** — matches `frontend` `npm run lint`  
- **Tailwind CSS IntelliSense** — `tailwindcss` v4 in frontend  
- **Docker** — optional, for editing/running `infra/docker-compose.yml`  

---

### 7. Optional tools (recommended)

**`sqlite3` CLI**  
Inspect `backend/dev.db` locally (unless `DATABASE_URL` points elsewhere).

Install: usually preinstalled on macOS; else [SQLite](https://www.sqlite.org/download.html)

**HTTP client**  
`curl`, [Bruno](https://www.usebruno.com/), or VS Code **REST Client** for hitting FastAPI routes.

**Algorand wallet / explorer**  
Pera, Lora, or AlgoExplorer-style tools to verify transactions (see `NETWORK` / Lora URLs in `app/api/routes.py`).

---

### ⚠️ Caveats

- **Postgres** in Docker Compose is **not wired** to the app’s SQLAlchemy URL; Redis is the compose service the code actually needs today.
- **`NETWORK`** does not configure Algod; RPC is fixed in `algorand_client_v2.py` unless you change that file.

**Dev API with `APP_ENV`:** `cd backend && APP_ENV=dev ./.venv/bin/python -m uvicorn app.main:app --reload`

## Economics docs

- Policy versioning and snapshot economics guide: `backend/app/economics/README.md`

## Tech debt

- Intentional deferrals and backlog (single source of truth): [`docs/tech-debt/README.md`](docs/tech-debt/README.md)