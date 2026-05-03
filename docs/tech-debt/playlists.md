# Playlists — Tech Debt & Future Work

Type: TECH_DEBT  
Focus: Playlists surface shipped as MVP (models, CRUD, minimal playback, session source fields). This file tracks **deferrals and gaps**, not current runtime truth — see `/docs/state/backend.md` and `/docs/state/streaming.md` for what is implemented today.

---

## 1. DISCOVERY INTEGRATION (PARTIALLY IMPLEMENTED)

**Current**

- **Candidate pool**: `get_playlist_candidates` feeds `build_candidate_set` — public playlists, `updated_at DESC`, up to **3** playable tracks per playlist (ordering + merge only; **no** extra scoring weight for the `playlist` **pool label** specifically).
- **Weak scoring signal**: `load_playlist_membership_counts` + `score_candidates` — count of **public, non-deleted** playlists per song; **`0.05 * log1p(count)`** added to **`score`** and **`for_you_score`** (discovery-only; **no** payouts).
- **Curated rail (MVP)**: `finalize_discovery_ranking` with `db` builds the curated section from public playlists (max **2** tracks per playlist, daily **deterministic** shuffle seed).

**What is still missing**

- **Rich playlist_stats** (materialized aggregates, recency-weighted inclusion, listen-weighted signals) — today counts are computed **on read** with one grouped query over `playlist_tracks` ⨝ `playlists`.
- **Featured / verified** playlist semantics vs any public playlist.
- **DB-backed curated snapshots** (immutable daily editorial), **curator roles** wired to discovery, and **advanced scoring** that weights curator or playlist metadata beyond the simple membership bump.

**Why it matters**

Playlists now surface in discovery as **candidates** and **curated ordering**, but there is no durable editorial contract, attribution of “official” curators, or economic linkage.

**Where it should integrate later**

- `discovery_ranking.py` / dedicated snapshot tables — precomputed curated lists per day or campaign.
- RBAC + admin flows — who may publish playlists that affect discovery rails beyond “public”.
- Optional scoring hooks — only with product policy (see §4).

**Future work**

- **Curated system v2**: DB-backed snapshots (audit trail, rollback), curator roles, campaigns, A/B or region flags.
- **Advanced scoring**: bounded, documented signals from playlist engagement or curator reputation — never silent payout coupling without policy (see §3).
- Eligibility rules beyond “public + not deleted” (e.g. minimum track count, verified curator only).

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

---

## 7. CURATED SOURCE DEPENDENCY (ARCHITECTURAL LIMITATION)

**Current behavior**

- Curated songs are derived from public playlists (see discovery finalize path).
- They are **only included if present in** `candidate_ids` (intersection with the discovery candidate universe).

**Implication**

- Curated is **not** a primary discovery source on its own.
- Strong playlist tracks that never enter the merged candidate pool are **never** shown in the curated rail.
- Curated ordering and reach **depend on** candidate pool composition (popular / user / playlist pool merge, caps, dedupe).

**Why it matters**

- Breaks **editorial independence**: playlist-driven “picks” cannot outrank the candidate gate.
- Limits **curator influence** relative to algorithmic pool construction.
- **Couples** two layers that are conceptually separate: algorithmic selection vs editorial/playlist narrative.

**Future solution**

- Treat curated as a **primary source**: eligible playlist tracks should be able to surface **without** requiring membership in `candidate_ids`.
- Reuse the same **discoverable / playable** filters as today, but resolve curated ids **directly** from playlists + those filters — not via the merged candidate list.
- Preserve compatibility with **ranking** (e.g. curated ids still excluded from algorithmic ranked slots as today) and **section caps** (`_MAX_SECTION_CURATED` and composition rules).

---

## 8. PLAYLIST STATS & SIGNALS (DEFERRED)

**Current**

- Membership **count** per song (public, non-deleted playlists) is computed at request time inside `build_candidate_set` / `score_candidates` inputs — adequate for a **weak** boost, not a product analytics layer.

**Future work**

- **`playlist_stats` system**: durable rows or cache (playlist-level listen aggregates, follower counts, last-updated decay) feeding discovery **without** per-request full scans at scale.
- **Batch aggregation**: offline or incremental jobs to maintain counts and recency-weighted metrics (e.g. exponential decay of inclusion importance).
- **Recency-based signals**: weight tracks by how recently they were added to influential playlists; tie-breakers keyed off playlist `updated_at` or editorial campaigns — policy-gated and documented separately from MVP `log1p(count)`.

---

## 9. PLAYLIST TRIPLE INFLUENCE (COMPOUNDING BIAS)

**Current behavior**

Playlists touch discovery in **three** largely independent layers:

1. **Candidate generation** — playlist candidate pool (`get_playlist_candidates` / merge into `build_candidate_set`).
2. **Curated section** — playlist-derived curated rail (`build_curated_ids_from_public_playlists` / finalize).
3. **Ranking** — `playlist_count` → `log1p` weak additive boost on `score` / `for_you_score`.

**Implication**

Tracks that appear in public playlists can accumulate **multiple advantages**:

1. Higher chance to enter the **candidate set** (pool merge).
2. **Curated** exposure (subject to intersection with candidates — see §7).
3. Extra **ranking** score from playlist membership breadth.

**Risks**

- **Compounding bias** toward playlist-included songs vs never-playlisted tracks.
- **Reduced diversity** if the same cohort dominates candidates, curated, and score ordering.
- **Reinforcement loops** (“rich get richer”) as playlist activity correlates with surfacing.
- **Weaker low-exposure guarantees** in practice if playlist-heavy tracks crowd out algorithmic exploration slots.

**Why it matters**

- Blurs the intended balance between **algorithmic discovery**, **exploration** (e.g. low-exposure paths), and **human / playlist curation**.
- Can skew the system toward **early playlist activity** and public-playlist density rather than listening-quality or editorial intent alone.

**Future mitigation options**

- Decouple curated from `candidate_ids` (curated as **primary source** — aligns with §7).
- **Cap** total playlist-driven influence per song across layers.
- **Diminishing returns** when a track already benefits from another layer (e.g. score vs curated).
- **Reduce or normalize** the ranking signal when the track is already in the curated set for that response.
- Stronger **cross-source diversity** constraints in section composition.
- Evolve from raw **counts** toward **curator trust** / verified editorial weighting (ties to §4 and §8).

**Status**

- **Accepted for MVP** — simple wiring, weak explicit score weight, bounded curated cap.
- **Requires monitoring** as traffic and playlist volume grow (metrics on overlap: pool ∩ curated ∩ high `playlist_count`).

---

## 10. Playlist mutation responses are not enriched

### Current state

- **`GET /playlists/{id}`** → **enriched** playlist payload: playlist metadata plus per-track **`title`**, **`artist_name`**, **`cover_url`**, **`audio_url`**, and top-level **`cover_urls`** (first four positions; entries may be `null`).
- **`POST /playlists`** and **mutations** (`POST /playlists/{id}/tracks`, `DELETE .../tracks/{song_id}`, `PUT .../reorder`) → **slim** response: same playlist metadata as before, but **`tracks`** entries are **`song_id`** and **`position`** only (no hydration).

### Implication

- The **frontend must refetch** **`GET /playlists/{id}`** (or equivalent) after a mutation when it needs enriched track rows (detail UI, collage, playback lists driven from hydrated fields).

### Why acceptable in MVP

- Avoids duplicating hydration on every write path and keeps mutation payloads small.
- Single enrichment code path stays tied to **GET** detail (`playlist_to_detail_enriched` / shared discovery-style batch hydration — see **`/docs/state/backend.md`**).

### Future improvement

- **Unify** mutation responses with GET shape (always enriched), **or**
- Add an **optional query flag** / variant (e.g. `?enriched=1`) on mutation responses for clients that want hydrated tracks without a second round-trip — trade payload size and server work vs UX.

---

### Add-to-playlist UX improvements

**Current (frontend MVP)**

- **Playlist modal** loads **`GET /playlists`** on open and adds via **`POST /playlists/{id}/tracks`** with single-select list (Tailwind-only UI).

**Future**

- **Recent playlist preselection** — remember last-used playlist(s) per user/session and highlight or default-select.
- **Multi-select playlists** — add the same track to several playlists in one confirm step (batch or parallel calls with clear partial-failure UX).
- **Search inside modal** — filter long playlist lists by title; optional sort (recently updated, A–Z).
