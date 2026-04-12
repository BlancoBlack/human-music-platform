# Human Music Platform

Event-driven Web3 music streaming platform.

## Stack

- Backend: FastAPI
- Frontend: Next.js
- Blockchain: Algorand
- Architecture: Event-driven

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

**Python 3.9+**  
Use the same major.minor Python on every machine (e.g. MacBook and Mac Studio). There is no `pyproject.toml` pinning a version.

Install: [python.org/downloads](https://www.python.org/downloads/) or `brew install python@3.12` (macOS)

#### Execution rule (backend)

All backend and worker commands assume:

1. **Current working directory is `backend/`** (the folder that contains `app/`, `worker.py`, and `requirements.txt`).
2. **Interpreter is always `backend/.venv`** — never the system Python, Homebrew `python3`, or a global `uvicorn` on `PATH`.

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

**Note:** `app/blockchain/algorand_client_v2.py` uses a **hardcoded** Algod URL (`https://testnet-api.algonode.cloud`) and empty token. Changing `NETWORK` does not switch RPC endpoints; use that only for explorer URLs.

**Frontend (`frontend/.env.local`)**

| Variable | Purpose | Example |
|----------|---------|---------|
| `NEXT_PUBLIC_API_BASE` | FastAPI base URL for browser `fetch` calls | `http://localhost:8000` |

---

### 4. Database

**SQLite**  
Configured in `app/core/database.py` as `sqlite:///./test.db` (file **`backend/test.db`** when the working directory is `backend`).

**Schema**  
Created on API startup via `Base.metadata.create_all`; additional SQLite `ALTER TABLE` steps run in `main.py` for older files.

**Alembic**  
Not present; no migration CLI.

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
| `./.venv/bin/python scripts/seed_data_v2.py` | Seed data + V2 ledger (batch → snapshot → lines) |
| `./.venv/bin/python scripts/test_distribution_vs_ledger_parity.py` | Distribution vs ledger parity check |
| `./.venv/bin/python scripts/test_stream_concurrency.py` | Concurrent `/stream` smoke test (API must be running) |
| `./.venv/bin/python -m pytest tests/` | `backend/tests/` |

**Cursor / VS Code extensions (inferred)**  

- **Python** — backend development  
- **Pylance** — typing and IntelliSense for Python  
- **ESLint** — matches `frontend` `npm run lint`  
- **Tailwind CSS IntelliSense** — `tailwindcss` v4 in frontend  
- **Docker** — optional, for editing/running `infra/docker-compose.yml`  

---

### 7. Optional tools (recommended)

**`sqlite3` CLI**  
Inspect `backend/test.db` locally.

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