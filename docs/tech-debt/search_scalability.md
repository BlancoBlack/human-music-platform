> **Tech debt docs:** This file is part of the [tech debt index](./README.md). For priority and backlog placement, see the summary in [backend.md](./backend.md) (“Full-text / trigram search…”).

---

# Artist search scalability

## Current implementation

Featured-artist autocomplete uses **`GET /artists/search`** with a **case-insensitive substring match**:

- Pattern: `lower(name) LIKE '%' || lower(query) || '%'` (with `%`, `_`, and `\` escaped in the user input).
- **Fine for small datasets** (typical dev / early production catalogs).

## Limitations

- Leading-wildcard **`LIKE '%…%'`** does not use a normal B-tree index on `name`; the database tends toward **full table scans**.
- Cost grows roughly with **table size** and **request rate**, so latency and DB load can become noticeable as the artist table grows.

## Future solutions

| Option | Approach |
|--------|----------|
| **A — PostgreSQL + pg_trgm** | Move (or dual-write) artist data to Postgres; add a **GIN index on `name` using `pg_trgm`** for similarity / `LIKE` acceleration. Strong fit if the stack standardizes on Postgres. |
| **B — SQLite FTS5** | If you stay on SQLite, maintain an **FTS5 virtual table** (or external content table) synced to `artists.name` and query FTS for tokens/prefixes instead of `%…%` LIKE. |
| **C — External search** | **Algolia**, **Meilisearch**, **Typesense**, or similar: index artist `id` + `name` externally; API becomes a thin proxy. Best when you want ranking, typo tolerance, and scale without overloading the primary DB. |

Pick based on hosting, ops budget, and whether search is “good enough” SQL or a product feature (fuzzy match, popularity, etc.).

## When to upgrade

- **Rough threshold:** on the order of **> ~10k artists**, or sooner if profiling shows trouble.
- **Concrete triggers:** **P95/P99** search latency or DB CPU rising; **slow query logs** showing repeated full scans on `artists`; autocomplete **rate limits** hit under normal traffic.

Until then, keeping **strict `limit`**, **debounced** clients, and **short max query length** remains the right mitigation.
