# Playlists — Tech Debt & Future Work

Type: TECH_DEBT  
Focus: Playlists surface shipped as MVP (models, CRUD, minimal playback, session source fields). This file tracks **deferrals and gaps**, not current runtime truth — see `/docs/state/backend.md` and `/docs/state/streaming.md` for what is implemented today.

---

## 1. DISCOVERY INTEGRATION (NOT IMPLEMENTED)

**What is missing**

- Playlists are not part of candidate generation (`discovery_candidate_pools`, `build_candidate_set`).
- No playlist-derived ranking signals in `score_candidates` / section composition.
- The curated discovery rail still relies on a **static** allowlist (`DISCOVERY_CURATED_SONG_IDS`), not database playlists.

**Why it matters**

Without discovery wiring, playlists do not influence **reach**, **exploration**, or **editorial narrative** in-product — they are isolated catalog objects.

**Where it should integrate**

- `backend/app/services/discovery_candidate_pools.py` — new pool(s) from featured or user-visible playlists (respect playable-universe filters).
- `backend/app/services/discovery_ranking.py` — optional scoring inputs; replace or supplement `DISCOVERY_CURATED_SONG_IDS` with DB-driven playlist track lists.

**Future work**

- Integrate playlists into `discovery_candidate_pools` with explicit eligibility rules (public only vs owner-context).
- Define playlist-based scoring signals (recency, follower/listen proxies when those exist).
- Replace `DISCOVERY_CURATED_SONG_IDS` with DB-driven playlists or editorial flags.

---

## 2. STREAMING ATTRIBUTION (PARTIALLY IMPLEMENTED)

**Current**

- `ListeningSession` persists `source_type` and `source_id` (including default `source_type="direct"` when omitted).

**Limitations**

- No playlist-specific validation (e.g. `source_type="playlist"` vs shape of `source_id`).
- No analytics pipelines aggregate by source yet (`listening_events` unchanged by design).

**Why it matters**

Attribution is stored but **unused downstream** — product cannot yet measure “started from playlist X” reliably in dashboards without analytics joins.

**Where it should integrate**

- Analytics services / reporting SQL reading `listening_sessions` (not payout snapshots).
- Optional: future correlation with `GET /playlists/{id}/play` usage (logging only — keep economics path separate).

**Future work**

- Use source context in analytics queries and admin/creator insights.
- Enable playlist-level engagement metrics (starts, completion proxies via sessions/events).

---

## 3. ECONOMICS (NOT IMPLEMENTED)

**Current**

- Ledger V2 payouts and snapshots aggregate listening inputs by **user_id + song_id** (`snapshot_listening_inputs`, `payout_lines`).

**Missing**

- Playlist-level attribution in sealed snapshots.
- Curator / playlist-owner reward lines.

**Why it matters**

Curator incentives require **provable, conserved** allocation rules; bolting playlist IDs onto today's snapshot rows without policy risks breaking **cent conservation** and auditability.

**Where it should integrate**

- `snapshot_service.py` / `payout_v2_snapshot_engine.py` — only after a **versioned policy** decision (new snapshot dimensions or parallel attribution table).
- Never silently overload existing `line_type` constraints without migration + policy docs.

**Future work**

- Extend snapshot model **or** introduce a parallel attribution + settlement path audited against Ledger V2.
- Define curator reward mechanics (e.g. bounded pool %) with explicit caps and idempotency keys.
- Prove compatibility with batch sealing, settlement breakdown, and admin tooling.

---

## 4. CURATOR SYSTEM (NOT IMPLEMENTED)

**Current**

- RBAC seeds a **curator** role and `create_playlist` permission; **no** playlist routes enforce it (ownership is generic user-only).

**Missing**

- Curator-specific playlist semantics (verified curators, featured placement).
- Reputation or verification gates tied to discovery/trust.

**Why it matters**

Without activation, the role is **documentation-only** — cannot enforce “who may publish editorial playlists” or differentiate trusted curators.

**Where it should integrate**

- `deps.py` — optional `require_permission("create_playlist")` or layered checks for featured playlists.
- Discovery/editorial configuration — tie curated rails to verified curator content.

**Future work**

- Activate curator permissions on relevant mutations (opt-in per endpoint contract).
- Define curator verification and surfaces (admin vs self-serve).
- Connect verified curator playlists into discovery (see §1).

---

## 5. PLAYLIST PLAYBACK (LIMITED)

**Current**

- `GET /playlists/{playlist_id}/play` returns minimal metadata and ordered `{ song_id, position }` rows only.

**Missing**

- Track hydration (titles, artist names, media URLs, playable flags).
- Explicit linkage from playback discovery UI → `POST /stream/start-session` with `source_type` / `source_id` for playlist attribution.

**Why it matters**

Clients must currently stitch catalog/stream endpoints themselves — higher integration burden and risk of inconsistent playable-universe checks.

**Where it should integrate**

- Frontend player / queue layer calling `/play` then resolving tracks via existing catalog APIs (or a **thin** hydrated variant endpoint if added later).
- `POST /stream/start-session` body — pass playlist context when starting playback from a playlist queue.

**Future work**

- Optionally add a hydrated playback response **without** duplicating discovery hydration logic (shared helper).
- Integrate streaming start-session from playlist queue flows with consistent `source_*` fields.

---

## 6. PERFORMANCE / SCALING

**Missing**

- Playlist popularity counters and trend metrics.
- Hedging for **very large** playlists (deep pagination, lazy loading patterns).

**Why it matters**

Discovery and fairness tuning eventually need **usage signals**; naive full-track reads for huge playlists can stress API and serialization.

**Where it should integrate**

- `playlist_service.py` / dedicated read APIs — pagination, caps, or cursor patterns on `/play` and admin analytics.
- Optional aggregate tables or indexed metrics jobs if playlist-read volume grows.

**Future work**

- Add composite / covering indexes if query plans show hotspots on `(playlist_id, position)` at scale beyond MVP volumes.
- Track playlist usage (reads, unique listeners) via analytics pipeline — not on the hot payout path.
