# Home Discovery UX (V1)

**Status:** Product specification (V1)  
**Audience:** Product, design, full-stack  
**Companion:** Implementation audit lives in engineering notes / PRDs; this file is the canonical UX + philosophy document.

---

## 1. Product Vision

Home is **not** a Spotify clone. It is not optimized for a single north star such as “time spent” or “streams per session” at any cost.

Home is a **system of controlled tensions** between:

| Force | Role on Home |
| --- | --- |
| **Engagement** | Lower friction to start listening; respect attention without hijacking it. |
| **Fair discovery** | Resist permanent dominance of the same few tracks (“hits”). |
| **Human curation** | Anchor meaning, taste, and context that algorithms alone cannot carry. |
| **Personalization** | Reflect the listener without collapsing into a closed bubble. |
| **Economic sustainability** | Internal only in V1—payouts and fairness exist under the hood but are **not** surfaced as UX mechanics yet. |

**Discovery is not about maximizing clicks, but balancing cultural value, user engagement, and exposure fairness.**

V1 accepts imperfection: ranking can be simple if the **structure** of the page (four layers) encodes these tensions explicitly.

---

## 2. UX Philosophy

### Intended feeling

- **Play-first, then explore:** the first meaningful action is listening, not configuring or reading walls of copy.
- **Not infinite-scroll addiction:** scrolling reveals **bounded** modules with clear intent, not an endless dopamine strip.
- **Not passive autoplay:** nothing starts because the page loaded.

### Hard constraint: no autoplay

**No autoplay** means audio does not begin without an explicit user action (tap / click / keyboard equivalent on a clear play control).

Reasons:

1. **User safety** — unexpected audio levels, mastering differences, and accessibility needs.
2. **Intentional listening** — music deserves a conscious “yes” from the listener.
3. **Respect for music** — avoids treating tracks as disposable background fuel.

*(Note: advancing within a queue **after** the user has explicitly started playback is a separate product decision; V1 Home itself must not auto-start the first track.)*

### Ideal flow

1. **User enters** → sees an immediate, **playable** focal option (dominant play control, no auto-start).
2. **User scrolls** → encounters **unexpected** but bounded content (exploration + fairness).
3. **User slows down** → can go deeper on titles, artists, or curatorial framing.
4. **User connects** → paths toward **artist**, **curator** (future), or **scene** (future)—relationship, not only consumption.

---

## 3. Home Structure (V1)

Four main sections, top to bottom. Order matters: engagement first, fairness and humanity visible without burying them.

### 3.1 Play Now (Engagement Layer)

- **Position:** first visible module.
- **Content:** **1–10** tracks.
- **Interaction:** strong visual **Play** CTA; **no autoplay**.

**Logic (conceptual):**

- Draw from a **semi-random** pool of roughly the **top ~100** “relevant” tracks (relevance defined by simple rules in V1: published/playable, recency, light popularity—not a full ML model).
- Mix **popularity**, **user taste** (from history where available), and **randomness** so the block feels fresh but not chaotic.

**Goals:** reduce friction; credible entry point without dictating the entire session.

---

### 3.2 For You (Controlled Personalization)

- **Blend:** target **~70%** “relevant” (history, affinity) and **~30%** **exploration** (adjacent artists, newer uploads, deliberate noise).

**Signals (V1-realistic):**

- Listening history (songs / artists with meaningful listen validation where the pipeline supports it).
- **Artist similarity** — conceptual in V1; may be approximated by “same artist / co-credits / featured” until a real similarity graph exists.
- Basic behavioral signals: **skip**, **listen duration** (when instrumented consistently).

**Non-negotiable:** must **not** trap the user in a bubble. Exploration is a first-class ingredient, not an occasional Easter egg.

---

### 3.3 Explore (Fair Discovery Layer)

- **Label tone (example):** *“Ready to explore beyond the obvious?”*

**Content types:**

- **Lower-play** tracks (anti-hit: invert or soften pure popularity).
- **New releases** (recency-weighted among playable catalog).
- **Early signals** (when available: shallow engagement but growth velocity—stub in V1 if data is thin).

**Goals:** anti-hit concentration; surface **emerging** artists.

**Risk:** lower average familiarity → listeners may perceive “lower quality.” **Mitigation:** cap list length, pair with strong artwork/titles, and keep **Play Now** and **For You** reassuringly accessible above this module.

---

### 3.4 Curated (Human Layer — V1 simulated)

- **V1:** “Editor picks” — **static list**, **database flags**, or **semi-random** rotation from a small allowlist. Transparently humble labeling (“Staff picks”) beats fake authority.
- **Future:** real curators, bios, playlists, and social proof.

**Goals:** introduce **cultural context**; prove the product values **judgment**, not only scores.

---

## 4. Ranking Philosophy (Conceptual)

Even before implementation, a single conceptual score keeps engineering and product aligned:

```text
discovery_score =
  engagement_signal
+ fairness_boost
+ curator_signal
+ personalization
+ cultural_depth      (future)
+ human_verification  (future)
```

| Term | Meaning |
| --- | --- |
| **engagement_signal** | Valid listens, completion-ish proxies, repeat intent—**tempered** so it does not become pure popularity. |
| **fairness_boost** | Uplift for under-exposed tracks, time-decay for over-exposed ones, caps on repeated surfacing. |
| **curator_signal** | Human-selected weight, editorial campaigns, scene-based boosts. |
| **personalization** | User-specific affinity and exploration mix. |
| **cultural_depth** | Future: scenes, articles, liner notes, relationships between works. |
| **human_verification** | Future: verified creators, reputation, anti-abuse—not “blue check” vanity but **trust in discovery**. |

V1 may implement **only a shadow** of this formula in SQL and heuristics; the **formula still guides** what to log and what to build next.

---

## 5. Anti-Patterns (What We Explicitly Avoid)

- **TikTok-style infinite scroll** engineered for maximum passive retention.
- **Pure popularity ranking** as the default ordering everywhere.
- **Full personalization bubble** with no exploration budget.
- **Autoplay audio** on landing or on scroll-into-view without explicit play.
- **Opaque recommendation logic** — users and creators deserve **explainable buckets** (“Explore: low plays”, “Curated: staff pick”) even if the internal score is complex.

---

## 6. Future Extensions (Tech Debt / Roadmap)

*Listed for alignment only—not V1 scope.*

- Live listening feed (when scale and moderation exist).
- Curator economy (compensation, attribution, slates).
- Early-discovery **reputation** system (signal quality, not clout).
- **Anti-viral shock absorber** — dampen runaway loops that starve the long tail.
- Cultural depth engine (articles, scenes, geographic/cultural context).
- **Explorer vs passive** user modes (density of exploration modules).
- Human verification boost tied to **abuse-resistant** identity and artist trust.

---

## 7. Discovery System Architecture

Discovery is implemented as a **pipeline**, not as four independent database views. Each home section is a **consumer of shared candidate pools**, not a bespoke ranked list. That separation keeps latency predictable, prevents four competing full scans of `listening_events`, and makes **cross-section deduplication** and **rotation** tractable.

### 7.1 Candidate Generation Layer

**Why sections must not query the DB directly**

- **Cost amplification:** four sections × ad-hoc joins (songs, media, artists, events) multiplies work per page load and encourages duplicated logic that drifts over time.
- **Inconsistent exposure:** without a shared layer, the same track can be “eligible” under different heuristics in parallel queries, defeating fairness and dedup guarantees.
- **Ranking sprawl:** per-section “sort the whole catalog” becomes four mini recommenders, each tempted to scan large tables or sort on volatile columns.

Instead, a **candidate generation** step (batch, materialized snapshot, or a small number of bounded SQL reads) produces **finite pools** of track ids + minimal join metadata. Downstream code only **samples** from those pools.

**Candidate pools (canonical set for V1 architecture)**

| Pool | Definition (conceptual) | Typical backing (no ML required) |
| --- | --- | --- |
| **popular** | Broadly engaged, validated-listen–weighted or aggregate-backed “what the platform is actually hearing.” | `global_listening_aggregates` (and/or pre-rolled top-N tables), never raw event scans per request. |
| **user_based** | Tracks and artists aligned with this listener’s history and aggregates. | `listening_aggregates`, recent `ListeningEvent` slices (indexed, time-bounded). |
| **low_exposure** | Fair-discovery bias: long tail and emerging surface area. | Inverse or capped global totals, recency windows, “below median exposure” cohorts from aggregates—not “all songs sorted by rarity” each time. |
| **random** | Controlled entropy: breaks ties, prevents lock-in, supports exploration quota. | Seeded pseudo-random **permutation of pool indices**, not `ORDER BY RANDOM()` on base tables. |

Pools are **inputs**, not final UX. They may overlap in membership; deduplication is a **downstream** contract on the assembled home payload.

### 7.2 Section Sampling Strategy

Each visible section (**Play Now**, **For You**, **Explore**, **Curated**) defines:

1. **Which pools it may draw from** (e.g. Play Now: `popular` + `user_based` + `random`; Explore: `low_exposure` + `random`; For You: `user_based` + `popular` + `random` with a fixed exploration share).
2. **How many slots** it fills (hard caps from §3).
3. **Sampling weights** within the allowed union (e.g. 70/30 relevant vs explore for For You—implemented as draw quotas from `user_based` vs `low_exposure`/`random`, not as a second global ranker per section).

**Avoid direct ranking per section:** sections do not re-sort the entire catalog. They **draw without replacement from pre-bounded pools** (or from pre-sorted **short** pool heads produced once). “Ranking philosophy” (§4) informs **how pools are built and ordered when materialized**, not four separate live rank operations at render time.

### 7.3 Cross-section deduplication

**Invariant:** a given `song_id` appears **at most once** in the union of `play_now`, `for_you`, `explore`, and `curated` in a single `GET /discovery/home` response.

**Mechanism:**

- Maintain a **`used_ids`** set while assembling sections in a fixed order (product order: Play Now → For You → Explore → Curated, or explicit priority table).
- When sampling a section, **reject or skip** any pick already in `used_ids`; refill from the same pool’s iterator until quota met or pool exhausted.
- If a section runs dry, return **fewer items** or fall back to a declared pool order (e.g. refill Explore from `random` playable only after `low_exposure` is exhausted)—never duplicate a track to pad.

This guarantees a coherent “page” and prevents one hit from occupying multiple mental slots.

### 7.4 Rotation strategy

**Goal:** visible variety **day over day** without unbounded non-determinism for debugging or support.

- Use **seeded randomness** derived from stable inputs, e.g. `hash(user_id or anon_key, UTC_date_bucket, app_version)` so the same user sees a **stable draw within a calendar day** (or chosen window) and a **fresh permutation** when the date rolls.
- Apply the seed to: within-pool shuffle order, tie-breaking among equal-weight ids, and exploration slot fills.
- **Curated** may ignore rotation for strictly editorial campaigns, or use a **separate** seed/editorial version so marketing swaps are explicit.

Rotation applies to **sampling order**, not to rewriting aggregate facts nightly unless product chooses a refresh cadence for pool materialization.

### 7.5 Performance constraints

| Constraint | Rule |
| --- | --- |
| **No `ORDER BY RANDOM()` on production base tables** | Banned for large catalogs; use bounded pools + in-memory or seeded shuffle of **at most thousands** of ids, or shuffle indices after a **LIMIT**. |
| **No full table scans on hot paths** | Candidate generation reads **aggregates**, **precomputed top lists**, or **indexed time windows** (e.g. recent events per user), not whole-history scans per home load. |
| **Rely on aggregates** | Global and per-user listening totals and pre-rolled tops are the **source of truth** for popularity and exposure class; events are for **incremental updates** and analytics, not per-request discovery fan-out. |

Together, §7.1–7.5 define an architecture that scales with **pool refresh cost** (batch / incremental) rather than with **per-request ranking cost**, while honoring the product tensions in §1–§3.

---

## 8. Implementation Alignment (Current)

This section summarizes what is now implemented in code, to avoid drift between product intent and backend/frontend behavior.

### Pipeline implemented

`candidate generation → multi-score ranking → constrained ranking → structured/adaptive section selection → hydration/normalization → API response`

### Ranking + selection highlights

- Multi-score tracks include `play_now_score`, `for_you_score`, `explore_score`.
- Popularity scoring uses anti-viral normalization (`log(1 + popularity)`).
- Artist caps are enforced at ranking and section levels.
- Selection is no longer naive top-N slicing:
  - soft score buckets (`high`/`mid`/`low`)
  - deterministic pattern pool for `for_you`
  - constrained low-bucket injection + quality guard for `explore`
  - weighted top-5 entry pick for `play_now`

### Direction/context layer implemented

- Per-track optional `context_tag`:
  - `Fresh this week`
  - `Trending now`
  - `Hidden gem`
- Optional top-level `section_microcopy` map for frontend rendering.

### API shape (current)

`GET /discovery/home` returns:

- sections: `play_now`, `for_you`, `explore`, `curated`
- optional: `section_microcopy`
- per track: `id`, `title`, `artist_name`, `audio_url`, `cover_url`, `playable`, optional `context_tag`

### Frontend usage (current)

`/discovery` renders:

- section microcopy under section titles when present
- `context_tag` under artist line when present
- subtle visual hierarchy for lead `play_now` item
- safe fallback behavior when optional fields are absent

---

*End of V1 product specification (plus implementation alignment note).*
