Type: FUTURE_IDEA
Status: NOT_IMPLEMENTED
Linked State: /docs/state/discovery.md
Last Verified: 2026-04-29

# Discovery: Advanced System (Future Blueprint)

**Status:** Blueprint only — not implemented in V1  
**Audience:** Product, backend, economics, ML-adjacent platform roles  
**Related:** `docs/product/discovery-home-v1.md` (V1 UX), current backend discovery foundations (pools, optional auth, read-only aggregates)

---

## 1. Purpose

This document captures future discovery and ranking directions (V2+). It exists to:

- preserve advanced ideas without committing the codebase to them prematurely,
- separate research-grade mechanisms from the intentionally simple V1 path,
- flag dependencies on additional data infrastructure.

Nothing in this file is a specification for current work. Implementation tickets should reference explicit product decisions and schema migrations, not this blueprint alone.

### Current V1 gaps

- Missing rich metadata for ranking.
- No full curator identity/economy system.
- No cultural context graph layer.
- No real-time session re-ranking loop.
- Limited personalization signal depth.

---

## 2. Unified Objective Function

A future system might optimize:

**U = alpha * Rel + beta * Disc + gamma * Health**

Where:
- **Rel**: personalization affinity
- **Disc**: discovery value and long-tail uplift
- **Health**: ecosystem balance and concentration control

Weights require governance, experimentation ethics, and creator-facing transparency before production use.

---

## 3. Advanced Ranking System

### Baseline linear score (conceptual)

For candidate track i:

**Score_i = alpha * Rel_i + beta * Disc_i + gamma * Pop_i**

### Extensions

- Dynamic weights from user/session context.
- Session-position-aware ranking.
- Temporal/Bayesian smoothing to reduce rank flicker.

These are excluded from V1 due to explainability, operability, and data requirements.

---

## 4. Exposure Control System

Potential mechanisms:
- per-song daily exposure caps,
- per-user per-song caps,
- exponential decay penalties,
- diversity boosts,
- day pacing budgets,
- entropy-based slate objectives.

Excluded from V1 because trusted impression/surface pipelines are not yet first-class.

---

## 5. Quality Scoring System

Conceptual composite:

**Q = w1 * CR + w2 * (1 - ESR) + w3 * LD**

Possible additions:
- dynamic thresholds,
- cold-start sandboxing,
- progressive exposure scaling.

Excluded from V1 because these require richer event/session rollups and careful alignment with antifraud and payout truth.

---

## 6. Session-Based Dynamic Discovery

Stateful ranking ideas:
- per-session state updates from plays/skips/seeks/searches,
- inferred session intent,
- within-session rank adaptation.

Excluded from V1 due to real-time state complexity and consistency requirements.

---

## 7. Graph-Based Discovery

Future graph model across tracks, artists, curators, scenes, and eventually privacy-safe user aggregates.

Value:
- better cultural/contextual transitions,
- stronger human-in-the-loop editorial overlays.

Excluded from V1 due to graph infra and anti-gaming overhead.

---

## 8. Exploration vs Exploitation

Bandit-style framing can balance:
- reward (satisfaction),
- information gain (testing under-exposed items).

Requires robust experimentation infra and governance to avoid trust/payout distortions.

---

## 9. Why V1 Stays Simple

V1 prioritizes:
- debuggability,
- deterministic behavior,
- production safety,
- schema honesty.

Simplicity is a risk-control strategy.

---

## 10. Evolution Path (illustrative)

- **V1:** stable heuristic sections.
- **V2:** quality + richer batch signals.
- **V3:** explicit exposure governance.
- **V4:** graph/cultural intelligence layer.

Advance only when data and operational readiness exist.

## Related State
- /docs/state/discovery.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/discovery.md
