Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/frontend.md
Last Verified: 2026-04-29

# Tech debt: Product surface, growth, and differentiation

Business-facing and fan-facing capabilities **explicitly deferred** while core streaming + economics mature. Does not duplicate ingestion/player mechanics—see [ingestion.md](./ingestion.md), [player.md](./player.md), [ux.md](./ux.md).

---

## Monetization, pricing, and commercial model

**Description**  
Platform economics exist for **subscription pool → artist** distribution (see `docs/architecture` and economics modules), but a full **go-to-market monetization** layer (tiers, trials, geo-pricing, tax/VAT, storefront) is not scoped as a single shipped product surface here.

**Why it matters**  
Revenue capture and compliance are launch gates for a consumer music product.

**Current behavior**  
MVP paths focused on listening, catalog, and settlement plumbing.

**Proposed solution**  
Product roadmap workshop: pricing, payment provider, receipts, chargeback policy.

**Priority:** MEDIUM (HIGH when pursuing paying subscribers at scale)

**When to address:** After reliability and payout trust milestones.

---

## Artist onboarding (guided, wallet-aware, dashboard-first)

**Description**  
Artist flows exist (upload wizard, catalog, server forms for wallet fields), but there is **no** polished **first-run onboarding** product (identity verification story, wallet connect UX, rights declarations) as a cohesive funnel. Deferred wallet policy details live under [economics.md](./economics.md).

**Why it matters**  
Supply-side growth and support load depend on self-serve clarity.

**Current behavior**  
Functional paths for experienced operators; seed data uses dev wallet defaults.

**Proposed solution**  
Design onboarding state machine; integrate wallet UX and education; optional checklist in artist dashboard.

**Priority:** MEDIUM  

**When to address:** When recruiting non-technical artists or opening public signup.

---

## Dashboard UX and creator tooling depth

**Description**  
Artist-facing dashboards are **MVP-level** (balances, uploads, playback integration vary by page). Competitive products offer rich analytics, audience insights, and release tooling.

**Why it matters**  
Creator retention and perceived professionalism.

**Current behavior**  
Core data visible; polish and depth deferred.

**Proposed solution**  
Research-backed dashboard IA pass; prioritize metrics artists ask for first.

**Priority:** MEDIUM  

**When to address:** Post core streaming stability; parallel with [ux.md](./ux.md) home/IA work.

---

## Artist analytics onboarding bridge

**Description**  
Creator onboarding does not yet provide a complete guided bridge into analytics milestones and growth feedback loops.

**Why it matters**  
Artists need a clear transition from onboarding completion to actionable analytics signals.

**Current behavior**  
Onboarding and analytics capabilities exist as separate surfaces without a standardized guided bridge.

**Proposed solution**  
Introduce a creator onboarding-to-analytics progression with milestone-based guidance.

**Priority:** HIGH  

**When to address:** Before broad creator onboarding expansion.

---

## Public / partner API

**Description**  
Today the backend is primarily **application-driven** (Next.js + FastAPI). A **versioned public API** (API keys, rate limits, webhooks, SLAs) for partners or mobile clients is not a first-class product.

**Why it matters**  
Ecosystem integrations (labels, apps, ticketing) need stable contracts.

**Current behavior**  
Internal JSON/HTML endpoints; no documented public partner surface in tech-debt scope.

**Proposed solution**  
OpenAPI publish, auth model, sandbox tier, deprecation policy.

**Priority:** LOW (until partner demand)

**When to address:** After core user-facing app is stable.

---

## “Top cities” / geo analytics (blocked on data)

**Description**  
City-level charts require **IP or client geo** with privacy review, **geo-lookup** pipeline, and retention policy. **Not implemented**—no location fields assumed in current analytics paths.

**Why it matters**  
Storytelling and localized campaigns; must not violate privacy expectations.

**Current behavior**  
No user location ingestion documented for this purpose.

**Proposed solution**  
Privacy policy + coarse geo (CBDMA) + aggregated-only storage.

**Priority:** LOW  

**When to address:** When analytics roadmap explicitly requests geography.

---

## Fan score (lightweight, antifraud-friendly, private-first)

**Description**  
A **simple fan engagement score** (e.g. streams + active days + song diversity) could power **internal storytelling** and future personalization **without** public leaderboards at first. **Not implemented** as a named feature in codebase terms.

**Why it matters**  
Differentiation and antifraud signals; must stay simple to avoid gaming arms races early.

**Current behavior**  
Raw `ListeningEvent` data exists for aggregates; no dedicated “fan score” model or API.

**Proposed solution**  
Batch job or materialized view; start private/admin-only; document fairness review before any public ranking.

**Priority:** LOW  

**When to address:** After core analytics trustworthy; before social/recommendation features.

## Related State
- /docs/state/frontend.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/frontend.md
