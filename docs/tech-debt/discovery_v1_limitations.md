Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/discovery.md
Last Verified: 2026-04-29

# Discovery v1 Limitations

## 1. Overview

The discovery system is currently functional and stable, but not yet optimized for adaptive quality/exploration tuning.  
These limitations are intentionally deferred because current traffic/data volume is still early, and premature optimization would add complexity without reliable signal.

## 2. Exploration pressure (static vs dynamic)

**Current state**
- Exploration pressure is enforced with a fixed section minimum (`_LOW_EXPOSURE_SECTION_MIN_SHARE`).
- Low-exposure exposure is guaranteed through final-stage enforcement and reservoir fallback.

**Limitation**
- The share is static and does not adapt to user behavior or system performance.
- It does not respond to shifts in CTR or `listen_per_impression`.

**Why it matters**
- A fixed floor can over-enforce long-tail exposure in contexts where user intent is more head-focused.
- Over-enforcement risk: lower short-term engagement/UX in some cohorts.

**Future direction**
- Move to dynamic exploration pressure driven by observed performance.
- Tune by user segment (for example: new user vs returning user, high-engagement vs low-engagement cohorts).

## 3. Ranking quality signal (proxy vs real KPI)

**Current state**
- Ranking penalty uses a proxy quality signal derived from aggregate inputs (quality ratio over ranking aggregates).

**Limitation**
- The proxy is indirect and not the same as end-to-end discovery success.
- It can diverge from outcome truth metrics.

**Why it matters**
- Proxy-optimized ranking may not maximize validated listening outcomes.

**Future direction**
- Replace or augment proxy quality with direct discovery outcome KPIs:
  - `listen_per_impression`
  - `valid_listen_per_click`
- Keep antifraud-qualified outcomes as the source of truth.

## 4. Exploration vs quality tradeoff not adaptive

**Current state**
- Balance between exploration and quality is effectively fixed at runtime.

**Limitation**
- Same exploration/quality behavior applies broadly across different user states.

**Why it matters**
- New users and returning users often need different exploration intensity.
- Uniform behavior can be suboptimal for both retention and discovery depth.

**Future direction**
- Adaptive policy by user context:
  - onboarding/new user vs established listener,
  - engagement level and recent session quality.

## 5. Lack of experimentation framework

**Current state**
- No formal A/B testing layer for discovery strategy tuning.
- No lightweight config-driven runtime tuning for key knobs.

**Limitation**
- Strategy changes require code edits/deploys.
- Hard to isolate impact and compare alternatives safely.

**Future direction**
- Introduce a lightweight config/flag layer for discovery controls.
- Support controlled experiments for:
  - exploration percentage targets,
  - antifraud penalty strength/shape.

## 6. Analytics limitations (early-stage)

**Current state**
- Funnel metrics are structurally correct (impression -> click -> session -> valid listen) with dedupe/time-window hardening.

**Limitation**
- Data volume is still early for robust statistical confidence.
- Metrics are valid, but not yet strong enough for aggressive optimization loops.

**Why it matters**
- Premature tuning on low-sample data increases regression risk.

**Future direction**
- Keep collecting stable baseline data.
- Introduce confidence/guardrails before making automated or frequent parameter changes.

## 7. Not prioritized (explicitly)

These improvements are intentionally **not** being implemented now.

Current priority is:
- product usability and reliability,
- collecting real user behavior data,
- validating the current discovery system under live usage.

Optimization and adaptivity work should start after sufficient production signal exists to justify complexity.

## Related State
- /docs/state/discovery.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/discovery.md
