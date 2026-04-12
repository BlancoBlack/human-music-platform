# Tech debt: Infrastructure, operations, and quality gates

Runtime topology (DB, workers, queues, secrets), **observability**, and **test depth**. Cross-links: [backend.md](./backend.md) for Postgres ingestion locks and rate limits; [economics.md](./economics.md) for payout audit exports.

---

## Observability: structured logs, health checks, metrics

**Description**  
Important paths emit **Python `logging`** events with `extra={...}` dictionaries (e.g. `stream_request_received`, `ingestion_lock_*`)—useful, but not a full **structured logging** stack (JSON to stdout, correlation middleware, trace IDs on every request). There is **no** dedicated **`/health` or `/ready`** route surfaced in `routes.py` for orchestrators, and **no** Prometheus-style **metrics** endpoint wired in code today (architecture docs may mention Prometheus as a future direction).

**Why it matters**  
Production incident response, SLOs, and autoscaling depend on consistent signals—not only tailing unstructured logs.

**Current behavior**  
Standard logging; some high-value events have structured `extra` fields.

**Proposed solution**  
- JSON logging + request ID middleware.  
- Liveness/readiness endpoints (DB + Redis checks).  
- RED metrics or OpenTelemetry exporter—pick one stack and document in deployment guides.

**Priority:** HIGH  

**When to address:** Before multi-instance or paid production traffic.

---

## Production database: Postgres migration + hardening bundle

**Description**  
Application today targets **SQLite** for the main app DB in typical dev flows; `infra/docker-compose.yml` may include Postgres for experiments, but **economic ingestion on Postgres is not serialization-safe** until the work in [backend.md](./backend.md) (“PostgreSQL ingestion serialization”) ships. Moving to Postgres also implies backups, migrations, connection pooling, and failover design.

**Why it matters**  
SQLite does not match horizontal scale and concurrent writer expectations of a public streaming service.

**Current behavior**  
SQLite + documented skip of ingestion locks on non-SQLite dialects.

**Proposed solution**  
- Planned migration: Alembic/SQLAlchemy URL switch, data migration, load test.  
- Same release train: **ingestion locks**, **rate limiter** backing store ([backend.md](./backend.md)), and runbook.

**Priority:** CRITICAL for **scaled production**  

**When to address:** When horizontal API replicas or managed Postgres becomes the baseline.

---

## Job queue and workers (RQ today; scale-up path)

**Description**  
The codebase uses **Redis + RQ** (`app/core/queue.py`, `worker.py`) for async jobs—not Celery. That is **sufficient for MVP**, but ops may later want Celery, Dramatiq, or managed queues for retries, crons, and visibility.

**Why it matters**  
Worker crashes, poison messages, and backlog metrics need operator-grade tooling at scale.

**Current behavior**  
Redis on localhost in default config; separate worker process documented in root `README.md`.

**Proposed solution**  
- Harden Redis URL from env, auth, TLS for cloud.  
- Re-evaluate queue library when job volume or complexity crosses RQ comfort zone.

**Priority:** MEDIUM  

**When to address:** Pre-production or first multi-region staging.

---

## Secrets and configuration management

**Description**  
`.env` / `.env.example` patterns exist; production still needs **rotation**, **per-environment secrets stores** (Vault, AWS Secrets Manager, etc.), and **least-privilege** API keys for chain and indexers.

**Why it matters**  
Leaked settlement keys or DB URLs are existential incidents.

**Current behavior**  
Developer-oriented env files; see root `README.md` and `backend/.env.example`.

**Proposed solution**  
Document target secret backend; never log secrets; inject via platform in CI/CD.

**Priority:** HIGH  

**When to address:** First deploy beyond trusted dev machines.

---

## End-to-end and blockchain-sandbox integration tests

**Description**  
Test suite today is **unit/integration-scoped** modules (`backend/tests/`—e.g. settlement with mocked Algorand, media upload, rate limits). There is **no** automated **full journey** test: seed → stream sessions/checkpoints → finalize → snapshot → payout line → settlement worker → (sandbox) chain confirm → UI assertion.

**Why it matters**  
Regressions at the glue layer (idempotency, locks, worker, API) are exactly what E2E catches.

**Current behavior**  
Focused pytest modules; manual scripts under `backend/scripts/` for deeper probes.

**Proposed solution**  
- Dockerized CI job: API + Redis + worker + ephemeral SQLite or test Postgres.  
- Optional: Algorand **sandbox** funded account for one happy-path settlement test behind a flag.

**Priority:** HIGH  

**When to address:** After core APIs stabilize; before declaring payouts “production ready.”

---

## Reproducible developer setup (continuous improvement)

**Description**  
Root `README.md` already documents Docker Compose for Redis, venv + `pip install -r requirements.txt`, `backend/.env.example`, uvicorn, worker, and frontend `npm ci`—a solid baseline. Remaining gaps are **subjective**: one-command `make bootstrap`, pinned Node/Python in CI identical to local, documented ports and health expectations.

**Why it matters**  
Onboarding friction slows contributors and makes CI failures opaque.

**Current behavior**  
Multi-step manual quickstart; `.env.example` exists for backend.

**Proposed solution**  
Optional Makefile or `scripts/dev-up.sh`; CI matrix verifies quickstart steps.

**Priority:** LOW  

**When to address:** When contributor count or CI churn justifies it.
