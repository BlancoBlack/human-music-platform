# Tech debt: Economics, payouts, and audit trail

Ledger, settlement, policy traceability, and **deferred product/legal** choices that affect money movement. Complements [backend.md](./backend.md) (API/scale) and [ingestion.md](./ingestion.md) (listening pipeline).

---

## Artist payout wallet: seed default vs real onboarding (product + ops)

**Description**  
Seeding (`seed_common` / `seed_data_v2`) assigns a **shared dev wallet** to artists when `payout_wallet_address` is empty—appropriate for **local/dev**. Artists can also set **`payout_wallet_address`** via existing server-rendered / form flows (`routes.py`). What is **not** decided yet: whether a wallet is **required** for onboarding, **custodial vs self-custody**, and **fallback treasury** behavior when no wallet is provided.

**Why it matters**  
Production payouts and compliance depend on a clear wallet story; ambiguous defaults risk misdirected funds or blocked settlements.

**Current behavior**  
Dev seed fills a known Algorand address; runtime forms allow manual entry; settlement paths already treat missing wallet as a failure mode in worker logic.

**Proposed solution**  
- Product spec: required wallet vs optional + treasury sink; document in onboarding.  
- Optional: guided wallet connect flow on the modern frontend (beyond HTML admin forms).

**Priority:** HIGH (before production payouts at scale)

**When to address:** When replacing seed-only artists with real users; align with legal/compliance.

---

## Public “artist” vs future `rights_parties` (legal / payment entity)

**Description**  
Today **`artists`** is the public identity tied to catalog and payouts. A fuller music business model often splits **public performer** from **legal rights holder / payee** (label, publisher, PRO).

**Why it matters**  
Wrong entity on a chain transfer is hard to unwind; splits and tax reporting need the correct counterparty.

**Current behavior**  
Single `Artist` model carries payout fields and catalog ownership; no separate rights-party graph.

**Proposed solution**  
Defer until KYC/partner requirements force it: introduce `rights_parties` (or similar) with FK from songs/recordings; migrate payout targeting. **Explicitly not** required for current MVP velocity.

**Priority:** LOW (until label/KYC scope)

**When to address:** After core streaming + payout reliability; when contracts require it.

---

## Economic policy versioning: snapshots vs live `validate_listen` (dual sources)

**Description**  
**V2 snapshots** already capture strong traceability: `PayoutInputSnapshot.policy_id`, `policy_json`, `antifraud_version`, `listening_aggregation_version`, and derived `policy_artist_share` / lambda fields—see `snapshot_service.build_snapshot`. Separately, **`validate_listen`** (listening path) encodes thresholds, daily cap, spacing, and `exp(-0.22 * repeats)` with **literals in code**, not via `get_policy()`—so antifraud parameters can **drift** from `app.economics.policies` if one side is updated without the other. Subscription pool math still uses `economics_constants.ARTIST_SHARE` in legacy payout paths—another axis to reconcile with policy objects over time.

**Why it matters**  
Auditors and engineers need **one authoritative story** for “which rules produced this `ListeningEvent` row vs this snapshot row.” Drift undermines reproducibility and incident response.

**Current behavior**  
Snapshot/build path is versioned; per-event validation is **not** policy-parameterized in code today.

**Proposed solution**  
- Thread `policy_id` (or frozen rule bundle) into listen validation at ingest time **or** document immutable coupling and add CI checks that literals match `POLICIES["v1"]`.  
- Long-term: single module reads `EconomicPolicy` for both validation and snapshot builders.

**Priority:** CRITICAL (for “money on the line” audits); **HIGH** if v1 constants are treated as immutable forever.

**When to address:** Before widening policy experiments beyond controlled scripts; ideally **pre-production** hardening.

---

## Settlement breakdown export and external verification

**Description**  
Settlement stores **`breakdown_json`** and a **`breakdown_hash`** (`compute_breakdown_hash`) with immutability checks in the worker—strong **internal** integrity. There is **no** first-class **HTTP download** of breakdown packages for external auditors, block explorer linking, or third-party **hash verification** UX.

**Why it matters**  
Transparency and dispute resolution benefit from exporter tooling and documented verification steps.

**Current behavior**  
Hash in DB + logs; verification logic exists in Python for tests / worker paths.

**Proposed solution**  
- Authenticated `GET` (or admin) endpoint: JSON breakdown + hash; manifest format versioned.  
- Public doc: how to recompute hash offline; optional explorer deep links when on-chain refs exist.

**Priority:** MEDIUM  

**When to address:** When opening payouts to external partners or running public beta with accountability promises.
