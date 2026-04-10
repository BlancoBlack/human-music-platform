# Tech debt: Backend

API services, SQLite-oriented patterns, and scale assumptions. Economic validation (`validate_listen`, `ListeningEvent`) is intentionally out of scope unless noted.

---

## Distributed / shared rate limiting (currently in-memory)

**Description**  
`POST /stream`, checkpoint, and start-session rate limits use **process-local** deques (`threading.Lock` + dicts). Multiple uvicorn workers or horizontal replicas do **not** share counters.

**Why it matters**  
Under production load balancers, per-IP/user limits become porous; abuse and accidental self-DOS risk rise.

**Current behavior**  
Correct for single-process dev; documented in code comments for SQLite vs Postgres.

**Proposed solution**  
- Redis (or similar) sliding windows keyed by user / IP / route class.  
- Or centralized gateway (API Gateway, Cloudflare) for coarse limits + app-level fine limits.

**Priority:** HIGH  

**When to address:** **Before multi-instance production** or public launch at scale.

---

## Full-text / trigram search for artist (and catalog) scaling

**Description**  
Artist search and listing may need FTS, trigram (`pg_trgm`), or dedicated search (OpenSearch, Meilisearch) as catalogs grow.

**Why it matters**  
SQLite `LIKE` and simple indexes do not scale to fuzzy, ranked search.

**Current behavior**  
`GET /artists/search` uses case-insensitive substring `LIKE '%query%'`. **Detailed write-up:** implementation, limitations, option matrix (Postgres pg_trgm, SQLite FTS5, external search), rough scale thresholds, mitigations (`limit`, debounce, max query length), and upgrade triggers are documented in [search_scalability.md](./search_scalability.md).

**Proposed solution**  
- Pick stack (stay SQLite + FTS5 vs Postgres vs external index); migrate query layer; add relevance ranking.  
- Use [search_scalability.md](./search_scalability.md) as the technical reference when executing.

**Priority:** MEDIUM  

**When to address:** When artist/song count or query latency crosses an agreed SLO (**post-MVP**); see triggers in [search_scalability.md](./search_scalability.md).

---

## Stronger session lifecycle model (`active` / `expired` / `finalized`)

**Description**  
`listening_sessions` has `finalized_at`, `song_id`, timestamps, but no explicit **state machine** column enforced everywhere. Checkpoint expiry and finalize eligibility are inferred from timestamps and triggers.

**Why it matters**  
Clear states simplify APIs, admin tools, and client recovery (“can I still checkpoint this id?”).

**Current behavior**  
Implicit: finalized if `finalized_at` set or `ListeningEvent` exists; checkpoint 410 if idle.

**Proposed solution**  
- Add `status` enum + transitions (e.g. `active` → `expired` on first 410 path server-side optional, `finalized` on event insert).  
- Migrate + backfill from existing data.

**Priority:** MEDIUM  

**When to address:** **Post-MVP**; pairs with **ingestion policy** and **session recovery API**.

---

## Optional checkpoint validation tightening

**Description**  
Further rules could bind `position_seconds` to song duration, detect impossible jumps, or correlate with engaged time server-side (heuristics only—client remains untrusted).

**Why it matters**  
Extra fraud signals without changing economic source of truth (`ListeningEvent`).

**Current behavior**  
Checkpoints store sequence + position; no strong correlation to master duration beyond client honesty.

**Proposed solution**  
- Soft warnings / flags on row or side table.  
- Hard reject only with product approval (could break legitimate clients).

**Priority:** LOW  

**When to address:** **Fraud review phase**; not blocking MVP.

---

## PostgreSQL ingestion serialization (multi-writer)

**Description**  
`stream_service` documents TODO: SQLite uses `ingestion_locks`; other dialects may not serialize `(user_id, song_id)` writers equivalently.

**Why it matters**  
Race conditions could theoretically produce two valid-looking events without proper locking under Postgres.

**Current behavior**  
Warning + skipped lock on non-SQLite dialects per code comments.

**Proposed solution**  
Implement `FOR UPDATE` or advisory locks as spec’d in `stream_service.py` TODO.

**Priority:** CRITICAL for **Postgres production**  

**When to address:** **Before** switching economic traffic to Postgres multi-worker.
