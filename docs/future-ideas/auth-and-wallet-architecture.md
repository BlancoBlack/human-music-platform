Type: FUTURE_IDEA
Status: NOT_IMPLEMENTED
Linked State: /docs/state/auth.md
Last Verified: 2026-04-29

# Auth + Wallet Architecture (Future)

**Status:** Deferred beyond current MVP  
**Current production baseline:** JWT + refresh (httpOnly cookie) + email/password.  
**Legacy note:** `X-User-Id` is deprecated and off by default (`ENABLE_LEGACY_AUTH=false`).

---

## 1. Why custodial wallets are deferred

- Custody expands trust, legal, and operational risk.
- DB-stored decryptable key material is a high-risk design.
- Safe custody requires KMS/HSM or MPC/custody vendor, isolated signing, and strong auditability.

---

## 2. Architecture options

### A. Custodial with KMS (self-operated)
- Pros: maximum control.
- Cons: maximum security/legal liability.

### B. Web3Auth / vendor-managed models
- Pros: smoother auth UX depending on mode.
- Cons: not a drop-in replacement; trust/custody model must be explicit.

### C. External wallet connection
- Pros: self-custody and reduced platform custody risk.
- Cons: pushes blockchain complexity to users unless strictly optional.

### Directional recommendation

Use MPC/custody API (or strong KMS-based custody as fallback) for invisible payouts, with strict destination snapshot rules at settlement boundaries.

---

## 3. Security minimums for activation

- KMS/HSM-backed key lifecycle and rotation.
- Isolated signing service with strict allowlists and transaction limits.
- Immutable-ish audit trails for wallet/signing events.
- Session/token hardening with refresh-family controls.
- Strong rate limits for auth and wallet mutations.

---

## 4. Future auth expansion

- OAuth2 provider linking (e.g., Google) with robust account-link policy.
- Web3Auth only after wallet trust model is finalized.
- Device/session binding for higher-risk surfaces.
- Session inventory and revoke-all support.
- Full retirement of legacy header auth path.

---

## 5. Migration outline

1. Freeze payout destination snapshot semantics at settlement.
2. Introduce canonical wallet identity model linked to `User` / `Artist`.
3. Ship isolated signing service pilot.
4. Dual-write migration window.
5. Cutover to verified wallet mutation rules.
6. Remove legacy auth header path once telemetry confirms no remaining clients.

---

## 6. Risks

- Legal/custody compliance burden.
- Security blast radius if keys/signing are weakly isolated.
- UX burden if wallet/network details leak into core flows.
- Reconciliation complexity with changing wallet destinations.

## Related State
- /docs/state/auth.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/auth.md
