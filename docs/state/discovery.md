# Discovery — current implementation

## AUDIT SNAPSHOT (2026-04-29) — Studio/Role/Economics Cross-check

## CURRENTLY IMPLEMENTED

- Discovery serving and telemetry pipeline is active and separate from studio creator dashboard APIs.
- Discovery quality analytics are computed from telemetry + listening validity joins; this is operationally distinct from payout settlement truth.

## PARTIALLY IMPLEMENTED

- Admin discovery analytics page exists in frontend, but backend protection posture for admin analytics route appears incomplete.

## NOT IMPLEMENTED

- No integrated discovery -> creator payout explanation layer in UI that clarifies which metrics are engagement diagnostics vs settled earnings.

## KNOWN ISSUES

- Discovery admin analytics endpoint guard gap should be resolved to align admin intent with enforced authorization.

## TECH DEBT — Global like signal (tuning & intent)

**Status:** Implementation is stable (loader, maturity window, cap toggle, playlist correlation damp, admin **`likes.ranking_context`**). **Tuning and intent quality are deferred** — current production/seed data volume is typically **too low** to observe a meaningful **`like_signal` / `like_boost` distribution** or contribution mix vs playlist / reorder in **`/admin/discovery`**.

1. **`LIKE_BOOST_ALPHA` (~0.012)** — heuristic; **not** validated against a real distribution or measured ranking impact. **Future:** use admin histograms + contribution table once traffic is sufficient; adjust alpha relative to playlist/reorder contribution and guardrails (no premature optimization before data).

2. **Intent vs casual like** — likes are **state rows** (`like_events`); **10-minute maturity** only filters very fresh taps. It does **not** separate weak vs strong intent or passive vs active engagement. **Future exploration (do not implement until data supports it):** like × listen correlation, persistence over time, repeated play/replay/save signals — **only after** patterns are observable at scale.

**Prerequisites before changing constants or semantics:** (a) sufficient likes (real usage or controlled seed/simulation), (b) review **`/admin/discovery`** distributions and correlations, (c) then data-driven alpha and optional richer intent features.

## ⚠️ SYSTEM INCONSISTENCIES

- Discovery analytics can be perceived as economic performance signals, but settlement-truth payouts are managed by separate ledger workflows; this separation is technical but not always explicit in product surfaces.

## CURRENTLY IMPLEMENTED

### API

- **`GET /discovery/home`** (`discovery_routes.py`): optional Bearer via `get_optional_user` (anonymous allowed).
- **`POST /discovery/first-session`**: authenticated onboarding entrypoint that reuses discovery candidate/scoring pipeline, prioritizes diversity (dedupe by artist), filters to playable tracks, returns `{ tracks, mode: "onboarding" }`, and is reentrant for onboarding resume (`PREFERENCES_SET` advances to `DISCOVERY_STARTED`; `DISCOVERY_STARTED`/`COMPLETED` are accepted idempotently).
- **Pipeline** (in order): `build_candidate_set` → `score_candidates` → `finalize_discovery_ranking` → `compose_discovery_sections` → `build_discovery_home_sections`. Playlist tracks feed the candidate merge **and** a batched **playlist membership count** per song; **`playlist` pool label** still does not change section formulas beyond shared scoring fields below.
- **Response**: sections `play_now`, `for_you`, `explore`, `curated` with hydrated track payloads; includes `timings_ms` (`pool_ms`, `ranking_ms`).
- **`GET /discovery/admin/analytics`**: read-only aggregates for internal ops (same route powers Next **`/admin/discovery`**). Includes **`signal_snapshot`** — no new tables: **14d** reorder aggregates (same weighted formula as **`load_reorder_signal_by_song`**: join **`playlists`**, clamp, liked downweight), **`reorder.scale`**, reorder histogram, **top 50** reorder songs; **likes** overview + **top 50** liked songs (**matured** same as ranking — see like signal below) with **`title`**, **`artist_name`**, and display **`artist`** alias; **`likes.ranking_context`**: like_signal / like_boost **histograms** (sample up to 2000 songs), **playlist↔like correlation** stats (avg signals, % with both), and **avg global contributions** (playlist vs like boosts; reorder called out as user-scoped N/A in that sample); plus **`liked_share_of_weighted_sum`**, **`likes_reorder_overlap`**, **`top_reorder_coverage_in_discovery`**. **Limitations:** global aggregates only — no per-user “why was I ranked this?” explainability; endpoint auth posture remains as documented in KNOWN ISSUES. Top-artists and anomaly tables include **artist / song names** via batched lookups.

### Candidate generation (`discovery_ranking.build_candidate_set` + `discovery_candidate_pools`)

- **Universe**: playable songs — `Song.upload_status == "ready"`, `deleted_at` IS NULL, master audio `SongMediaAsset` present; release gating when `release_id` set (`Release.state`, `discoverable_at` vs now).
- **Playlist pool**: `get_playlist_candidates` — **public** playlists ordered by `updated_at` DESC; up to **3** playable tracks per playlist (`PlaylistTrack.position` order). Same playable filters as other pools. Candidates retain `candidate_pool_by_song == "playlist"` for telemetry only — **not** an extra weight tied to that label.
- **Merge order**: reserved low-exposure prefix (floor share, unchanged) → then `get_popular_candidates` → `get_user_candidates` → `get_playlist_candidates` → `get_low_exposure_candidates`; dedupe by first occurrence; cap **`_MAX_CANDIDATES = 500`**.
- **Data loaded**: global popularity per candidate (`GlobalListeningAggregate.total_duration`), per-user relevance (`ListeningAggregate.total_duration` for logged-in users), `artist_by_song`, `days_since_release` (from `Song.created_at`), `user_listened_artists` (distinct artists user has listened to via aggregates), **`playlist_count_by_song`** — per candidate, count of **public** playlists with `deleted_at` IS NULL that include the song (single `GROUP BY song_id` query; missing ids ⇒ count **0**), **`like_count_by_song`** — **`like_events`** per song where **`created_at`** is in **[14d cutoff, now − maturity]** (`load_like_signal_by_song`: matured likes only, default **10 minutes** minimum age so state rows reflect intentional holds more than accidental taps; missing ids ⇒ **0**), **`reorder_signal_by_song`** — per logged-in user, private short-term runtime aggregate from **`playlist_reorder_events`** via **`load_reorder_signal_by_song`**: **14-day** window, join **playlists** (owner + non-deleted), per-event **`min(delta, 5)`** with **×0.4** on private **Liked Songs** title match, then **`min(sum, 20)`** + **`log1p`** in Python; anonymous ⇒ empty map.

### Signal aggregator (`signal_aggregator.py`)

- **Separation**: **DB loaders** run in `build_candidate_set` only (`load_playlist_membership_counts`, `load_like_signal_by_song`, `load_reorder_signal_by_song`). **`compute_signal_contributions`** is **pure CPU** — no session, no queries — and is invoked from `score_candidates` per candidate.
- **Return shape**: nested **`user`** / **`global`** / **`total`** (see **Signal layers** and **Signal model** below). Ranking uses **`total.signal_score`** only; flat mirror fields on each scored row stay stable for logs and tooling.
- **Normalization asymmetry** (must not be “fixed” without an intentional ranking change): **playlist** uses raw public playlist count → **`math.log1p`** inside the aggregator. **Reorder** values are **already** capped and **`log1p`** in `load_reorder_signal_by_song`; the aggregator **must not** apply `log1p` again.
- **Weights / toggles**: `PLAYLIST_POPULARITY_ALPHA = 0.05`, `REORDER_BOOST_ALPHA = 0.02`, `LIKE_BOOST_ALPHA = 0.012`, **`LIKE_CAP = 100`** (soft cap before `log1p`; tunable), **`LIKE_CAP_ENABLED`** (when false, raw like count is uncapped before `log1p`), **`LIKE_PLAYLIST_CORRELATION_DAMP ≈ 0.7`** — when **`playlist_count > 0`**, **`like_boost`** is multiplied by this factor (temporary decorrelation vs playlist breadth; documented as non-final). Combined additive term `signal_score = global_signal_score + user_signal_score` where `global_signal_score = playlist_boost + like_boost` is added to both main `score` (after `quality_penalty` on `base_score`) and `for_you_score`.

### Signal layers

- **`user`**: signals derived from the **requesting user** only. Today: **`reorder`** — `signal` / `boost` from `load_reorder_signal_by_song` (empty for anonymous).
- **`global`**: **song-level** aggregates not conditioned on the current user. **`playlist`** — public playlist membership breadth; **`likes`** — **matured** **14d** `like_events` count per song (`raw`); **`signal = log1p(effective_raw)`** with **`effective_raw = min(raw, LIKE_CAP)`** only if **`LIKE_CAP_ENABLED`**; **`boost = LIKE_BOOST_ALPHA * signal`**, then **× `LIKE_PLAYLIST_CORRELATION_DAMP`** when **`playlist_count > 0`** (single `log1p` on likes). Does not replace playlist signal — both sum into `global_signal_score`.
- **`total`**: **`user_signal_score`** (= reorder boost), **`global_signal_score`** (= playlist boost + like boost), **`signal_score`** = **`user_signal_score` + `global_signal_score`**. Ranking math uses **`signal_score`** only; this decomposition is for observability and future signals without changing the additive contract.

### Signal model

- **Structured output** from `compute_signal_contributions`:
  - **`global.playlist`**: `raw` = integer membership count from the loader; `signal` = `log1p(raw)`; `boost` = `0.05 * signal`.
  - **`global.likes`**: `raw` = **matured** **14d** like count from `load_like_signal_by_song`; `signal` / `boost` as above (cap optional via **`LIKE_CAP_ENABLED`**, playlist damp when `playlist_count > 0`).
  - **`user.reorder`**: `signal` = float from `load_reorder_signal_by_song` (loader-normalized); `boost` = `0.02 * signal` (no second `log1p`).
  - **`total`**: `user_signal_score`, `global_signal_score`, `signal_score` — **guarantee** `signal_score == user_signal_score + global_signal_score` and `global_signal_score == playlist_boost + like_boost`.
- **Per-row payload** (`score_candidates`): flat keys include **`like_count`**, **`like_signal`**, **`like_boost`**; plus existing playlist/reorder/total mirrors; **`signals`** holds the full nested object.
- **Terminology**: **raw** = pre-transform count (playlist membership or like count); **signal** = magnitude into the boost (playlist `log1p(raw)`; likes `log1p(min(raw, cap))`; reorder loader-scaled); **boost** = weighted contribution within its sub-signal; **`global_signal_score`** sums global sub-boosts.

### Scoring (`score_candidates`)

- **No DB inside `score_candidates`**; playlist, like, and reorder maps are passed in from `build_candidate_set`.
- **Popularity signal**: `log1p` of global duration; min–max normalized across candidates (flat fallback `_FLAT_POP_DISC = 0.5`).
- **Playlist breadth (weak, non-economic)**: Implemented via **`signal_aggregator.compute_signal_contributions`**: `playlist_signal = log1p(playlist_count)`; additive **`0.05 * playlist_signal`** is part of **`signal_score`**, applied to the main **`score`** (after quality penalty) **and** to **`for_you_score`** so `finalize_discovery_ranking` sort stays consistent. Does **not** affect payouts, streaming, or ledger paths — discovery-only read.
- **Playlist reorder (personal, weak, normalized, capped, short-term, non-economic)**: orthogonal to public playlist breadth — from **`reorder_signal_by_song`** (per-event clamp to **5**, liked private title downweight **0.4**, **14d** window, then **`min(aggregate, 20)`** + **`log1p`** in the loader). The aggregator applies **`0.02 * reorder_signal`** only (no second `log1p`). Same **`signal_score`** addition to **`score`** and **`for_you_score`** only (not `play_now_score` / `explore_score`); missing id ⇒ **0**. No stats table, no async jobs, no payout or listening-ingest writes.
- **Relevance**: per-user listening duration normalized by max in candidate set (anonymous: zeros).
- **Per-candidate features** (non-exhaustive): `pop_i`, `disc_i` (1 − pop), `recency_i` (60-day horizon), `novelty_i`, `novelty_boost` for days < 7, deterministic `rand_i` from `Random(song_id)`, `exploration_boost` (1 if user never listened to that artist else 0), `early_engagement` aliased to `pop_i` in explore formula; signal observability: **`playlist_count`**, **`playlist_signal`**, **`playlist_boost`**, **`like_count`**, **`like_signal`**, **`like_boost`**, **`reorder_signal`**, **`reorder_boost`**, **`user_signal_score`**, **`global_signal_score`**, **`signal_score`**, nested **`signals`** (see **Signal layers** / **Signal model**).
- **Section scores**: `play_now_score`, `for_you_score`, `explore_score`; explore can set `explore_excluded` when popularity in top ~10% of log-pop among candidates (length ≥ 10) → `explore_score = -1.0`.
- **Blended `score`**: quality multiplier applied to a **`base_score`** (with candidates non-empty, effectively the same `for_you_score` formula for logged-in and anonymous; anonymous simply has zero relevance); then add **`signal_score`** (= user reorder + global playlist + global like boosts from **`signal_aggregator`**) to **`score`** and **`for_you_score`** as above.

### Finalize ranking (`finalize_discovery_ranking`)

- **Curated rail** (no scoring impact; read-only DB):
  - When the caller passes a SQLAlchemy session (`db`), curated ids are built by `build_curated_ids_from_public_playlists`: **public** playlists with `deleted_at` IS NULL, ordered by `updated_at DESC` (then `Playlist.id ASC`); up to **2** playable tracks per playlist (`PlaylistTrack.position` order, same discoverability filters as other pools); flattened list deduped by first occurrence; **deterministic shuffle** via `random.Random` seeded from SHA-256 of the **UTC calendar date** (`YYYY-MM-DD`); result capped at `_MAX_SECTION_CURATED` (**8**), then intersected again with `candidate_ids` in finalize (order preserved; duplicates dropped).
  - **`curated_ids`** / **`curated_utc_date`** kwargs support tests and deterministic overrides.
  - **`DISCOVERY_CURATED_SONG_IDS`**: used only when finalize runs **without** `db` (empty in-repo; static fallback for offline/unit callers).
- **Algorithmic list**: dedupe scored rows by `song_id` (best by sort key); sort by `_final_sort_key` (for_you_score DESC, rel DESC, pop_log ASC, song_id ASC).
- **Artist cap in ranked list**: **max 2 songs per artist** when building `ranked_candidate_ids` (excluding curated picks from this cap’s input set as specified in code).

### Section composition (`compose_discovery_sections`)

- **Structured + adaptive selection**: soft buckets (high/mid/low by normalized section scores), patterns for “For you” (token sequences `F`/`E` by `user_id % 3`), explore mid/low injection rules, `play_now` first pick weighted among top 5 by `play_now_score` with freshness/artist/jitter factors.
- **Per-section artist caps**: e.g. play_now `per_artist_cap=1` in main fill paths; for_you and explore use `2` in `_take_from_bucket` / `_fill_simple` as coded.
- **Context tags**: `_context_by_song` map — strings like “Fresh this week”, “Trending now”, “Hidden gem”, or `None` from heuristics on `days_since_release` and normalized pop.

### Hydration (`discovery_hydration.build_discovery_home_sections`)

- Batch-loads `Song` / `Artist` / `SongMediaAsset` (master + cover); builds public URLs via `public_media_url_from_stored_path`; missing rows become placeholders (`UNKNOWN_TRACK` / `UNKNOWN_ARTIST`, `playable: false`) from `build_placeholder`.
- Response normalized through `normalize_discovery_sections_response` / `normalize_discovery_track_row` for strict JSON types; attaches section **microcopy** strings; logs up to `_MAX_HYDRATION_WARNINGS` issues per request (`discovery_hydration_issue`).

## PARTIALLY IMPLEMENTED

### Versus a “four-layer” product model (algorithm / curators / community / reputation)

| Layer | In code today |
|-------|----------------|
| **Algorithm** | **Implemented** — pools, scoring, caps, buckets, section assembly as above. |
| **Curators** | **Partial (MVP)** — curated home section is filled from **public playlist track order** (see Finalize ranking); not a separate curator role, editorial flags, or snapshot pipeline yet. |
| **Community** | **Partial** — no follower graph or comments; **public playlists** supply candidate IDs **and** a weak **`log1p(playlist_count)`** scoring bump (breadth of inclusion across playlists), not engagement-weighted playlist analytics. |
| **Reputation** | **Not implemented** — no artist/user reputation score feeding ranking in reviewed modules. |

## NOT IMPLEMENTED

- **Multi-region or A/B flags** for discovery parameters: weights and caps are **constants** in `discovery_ranking.py` (not env-driven in that file).
- **Separate curator/community microservices**: everything runs in-process in the API worker for `GET /discovery/home`.

## KNOWN ISSUES

- **Determinism vs randomness**: scoring uses `random.Random(song_id)` for tie jitter; section picks use additional seeded `Random` instances — **reproducible per song/user context** but not “purely deterministic” across all Python versions if library changed (**minor**).
- **Curated vs microcopy**: section copy says “Selected by humans” while the MVP rail is **playlist-derived** (human intent only insofar as playlists are human-authored); future curator/snapshot product may tighten naming.
