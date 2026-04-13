# Discovery: Advanced System (Future / Tech Debt)

**Status:** Blueprint only — **not implemented** in V1  
**Audience:** Product, backend, economics, ML-adjacent platform roles  
**Related:** `docs/product/discovery-home-v1.md` (V1 UX), current backend discovery foundations (pools, optional auth, read-only aggregates)

---

## 1. Purpose

This document captures **future** discovery and ranking directions (V2+). It exists to:

- **Preserve** advanced ideas without committing the codebase to them prematurely.
- **Separate** research-grade mechanisms from the **intentionally simple** V1 path (bounded pools, aggregate-backed signals, fixed weights, no ML, no session re-ranking).
- **Flag** dependencies: most sections below assume **additional data infrastructure** (event rollups beyond current aggregates, exposure counters, graph stores, experiment assignment, online feature stores, or batch pipelines).

Nothing in this file is a **specification for current work**. Implementation tickets should reference explicit product decisions and schema migrations, not this blueprint alone.

### Current V1 gaps (explicit tech debt)

These items are intentionally **not solved** in current discovery:

- **Missing rich metadata (urgent):** selection/ranking still rely on limited catalog + aggregate signals; richer metadata pipelines (scene/style/mood/context) are deferred.
- **No curator system yet:** curated lane is allowlist/editorial simulation, not a full curator identity/economy flow.
- **No cultural context layer:** no graph- or scene-level cultural relationships yet.
- **No real-time signals:** no live session re-ranking / event-stream feedback loop in discovery response.
- **Limited personalization signals:** personalization mainly uses aggregate listening + lightweight artist novelty, not deep behavioral/contextual features.

---

## 2. Unified Objective Function

A future system might optimize a **single conceptual utility** instead of treating sections as isolated heuristics:

**Maximize** U = α·Rel + β·Disc + γ·Health

| Term | Meaning |
| --- | --- |
| **Rel** | **Personalization** — affinity to the listener (history, taste, context), tempered to avoid pure bubbles. |
| **Disc** | **Discovery** — value of surfacing under-heard or culturally important work (fairness, novelty, long-tail uplift). |
| **Health** | **Ecosystem balance** — long-term platform health: sustainable payouts, creator diversity, fraud resistance, user trust, and “anti-hit” concentration metrics. |

**Health** generalizes raw **Pop** (popularity): popularity is one input to ecosystem dynamics, but health can penalize runaway concentration, reward sustainable engagement, or encode policy (e.g. caps, diversity). V1 may use a fixed **Pop** proxy; **Health** is the deliberate generalization for later versions.

Weights α, β, γ (or a richer parameterization) would need governance, experimentation ethics, and creator-facing transparency strategy before production use.

---

## 3. Advanced Ranking System (Not in V1)

### Baseline linear score (conceptual)

Per candidate track *i*:

Score_i = α·Rel_i + β·Disc_i + γ·Pop_i

(Rel_i, Disc_i, Pop_i are normalized features; Pop may later fold into Health.)

### Extensions (future)

**Dynamic weights**

[α, β, γ] = f(user_state, session_state)

Examples of inputs: time-of-day, fatigue signals, explicit “explore mode,” new-user flag, catalog maturity, or compliance mode. **Why useful:** adapts exploration pressure without hand-tuning one global triple. **Why not V1:** harder to debug, reproduce support tickets, and explain to creators; requires logging and safe defaults.

**Session-based ranking**

S_i(t): score depends on time or position within a session (e.g. after skips, after long dwell, after queue edits). **Why useful:** reduces repetition and respects in-session intent. **Why not V1:** needs low-latency session state, risks inconsistent snapshots vs payout aggregates, increases coupling to the player.

**Smoothing**

S_smooth: temporal or Bayesian smoothing so ranks do not flicker when counts are small. **Why useful:** stability for small catalogs and early artists. **Why not V1:** adds parameters and delayed reaction to real trends; V1 prefers explicit bounds and deterministic rotation.

---

## 4. Exposure Control System (Not in V1)

Ideas to document (all require **new** or **heavier** data, not present as first-class fields today):

| Mechanism | Idea |
| --- | --- |
| **Per-song daily cap** | E_song_day ≤ cap_song — limit how often a song is **surfaced** (not the same as listens; needs impression logging or equivalent). |
| **Per-song per-user daily cap** | E_song_user_day ≤ cap_user — anti-fatigue and bubble control. |
| **Exponential decay penalty** | score′ = score · exp(−λ·E_song) — soft suppression as exposure grows. |
| **Diversity boost** | score″ = score + γ·(1 − share_artist) — penalize over-dominance of one artist in a slate. |
| **Pacing over the day** | E_t = cap · (t / T_day) — time-varying budget so morning ≠ evening surfacing pressure. |
| **Entropy objective** | H = −Σ p_i log p_i — optimize slate diversity / information; overlaps with bandit objectives. |

**Why excluded from V1**

- Current schema centers on **listening aggregates** and **catalog**; it does **not** store **impression** or **surface** counts per user/day.
- Exposure caps without a **trusted impression pipeline** invite gaming (client-reported “views”) or blind spots (server-only without player truth).
- Pacing and entropy tuning need **simulation** and **offline evaluation** before touching economics-adjacent surfaces.

---

## 5. Quality Scoring System (Not in V1)

### Conceptual composite

Q = w1·CR + w2·(1 − ESR) + w3·LD

Suggested interpretations (names are illustrative):

- **CR** — completion or engagement quality (e.g. validated listen depth).
- **ESR** — early skip rate or similar “bounce” proxy.
- **LD** — long dwell / replay signal (careful with causality and fairness).

### Advanced variants

- **Dynamic thresholds:** τ = μ + k·σ — gate low-quality tails using rolling distribution of Q (catalog- or cohort-relative).
- **Cold start sandbox:** new uploads get bounded exposure until Q stabilizes.
- **Progressive exposure scaling:** ramp caps as Q crosses tiers.

**Why excluded from V1**

- **CR, ESR, LD** require **event-level or session-level rollups** richer than current `ListeningAggregate` / `GlobalListeningAggregate` (which summarize validated economic duration, not full behavioral nuance).
- Quality gates must align with **fraud and validation** rules; otherwise discovery becomes a parallel truth to payouts.

---

## 6. Session-Based Dynamic Discovery (Not in V1)

**State model**

- state_t = f(state_{t−1}, actions) — actions: plays, skips, seeks, queue changes, searches.
- intent_t — inferred or explicit listening intent (e.g. focus vs background).
- S_i(t) — rank or eligibility that **updates within** the session.

**Mechanisms**

- **Momentum:** carry forward short-term taste without overwriting long-term profile.
- **Smoothing:** avoid rank jumps on every single event.
- **Windowing:** only recent events influence S_i(t) to limit memory and storage.

**Why excluded from V1**

- Requires **real-time** or **near-real-time** state, idempotent updates, and clear separation from **settlement-grade** listening truth.
- Increases operational complexity (race conditions, partial failures, mobile backgrounding).

---

## 7. Graph-Based Discovery (Future Vision)

**Graph**

G = (V, E) with nodes for **track**, **artist**, **curator**, **scene** (geography, genre, community), and later **user** (privacy-preserving aggregates only).

**Transitions**

P(v_j | v_i) — probabilistic or learned adjacency: “from this artist, which scenes or peers?” Enables **cultural** discovery beyond co-listening matrices.

**Why valuable**

- Surfaces **context** and **relationships** (scenes, curation chains) that linear scores miss.
- Supports human-in-the-loop editorial overlays on graph regions.

**Why not V1**

- Needs graph storage, refresh jobs, and anti-gaming design; not part of the current ranking surface.

---

## 8. Exploration vs Exploitation

**Bandit framing**

- Treat slate selection as balancing **reward** (satisfaction, completion) vs **information gain** (trying under-tested tracks).
- Requires a **reward definition** aligned with product ethics (not pure listen maximization).

**Infrastructure**

- Assignment, logging, and analysis pipelines (A/B infra, holdouts, guardrails).

**Why not V1**

- Experimentation without guardrails can **distort payouts perception** and creator trust. V1 stays **deterministic** and **explainable** at the bucket level.

---

## 9. Why V1 Is Intentionally Simple

| Principle | V1 stance |
| --- | --- |
| **Debuggability** | Small number of moving parts; support can reason about “pools + weights + rotation.” |
| **Determinism** | Seeded or bucketed stability beats per-request stochasticity for reproducing issues. |
| **Production safety** | Read-only discovery, **aggregate-aligned** reads, no new economic side effects from ranking experiments. |
| **Schema honesty** | No pretending we have impression caps or completion rates we do not store. |

Simplicity is a **risk control** strategy, not a lack of ambition.

---

## 10. Evolution Path

| Version | Focus | Typical additions (illustrative) |
| --- | --- | --- |
| **V1** | **Current** — pools, multi-score heuristics (`play_now`/`for_you`/`explore`), anti-viral log normalization, structured/adaptive selection, dedup, direction layer (`context_tag` + section microcopy); **no ML**, no exposure tables, no session rank. | Ship, measure, instrument *surface* minimally if needed. |
| **V2** | **Quality + richer signals** — batch rollups for Q-like metrics; dynamic τ; cold-start sandbox; better cold catalog behavior. | New **materialized** tables or nightly jobs; still mostly batch, not online bandits. |
| **V3** | **Exposure control** — impression and cap models; decay and diversity in slates; optional pacing. | **Impression logging**, privacy review, anti-gaming, creator dashboards for *surfacing* not only streams. |
| **V4** | **Graph + cultural layer** — scenes, curators as first-class; graph walks + editorial regions; deeper exploration/exploitation with strong governance. | Graph store, content pipeline, moderation scale, ethical review for personalization. |

**Ordering discipline:** advance versions only when **data exists** to support the mechanism and when **downstream** (economics, support, creators) can absorb the complexity.

---

*This document is a living **north-star** catalog. Update when major architectural decisions change; do not treat it as an implementation checklist without product sign-off.*
