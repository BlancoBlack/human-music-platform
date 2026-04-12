# Auth + wallet (deferred architecture)

**Status:** Postponed beyond current MVP. The app ships **JWT + refresh (httpOnly cookie) + email/password**. **`X-User-Id` for listening is deprecated** and **off by default** (`ENABLE_LEGACY_AUTH=false`); opt-in only for legacy clients. **No custodial chain wallets** and **no Web3Auth** in production yet.

**Related:** Payout destination today is **`Artist.payout_wallet_address`** (settlement worker); any future “user wallet” must reconcile with that model (snapshot destination at batch finalization, single source of truth).

---

## 1. Wallet system (deferred)

### Why custodial wallets were not implemented

- **Trust boundary:** Server-generated keys + DB-stored material (even encrypted) make any **DB + app config leak** a plausible **total loss** event for user funds.
- **Operational/legal surface:** True custody of user assets triggers **licensing, AML/KYC, terms, and incident response** obligations that are out of scope for the current product phase.
- **Engineering cost:** Safe custody requires **KMS/HSM or an MPC/custody vendor**, a **dedicated signing service**, and **audit/reconciliation**—not a column on `users`.

### Risks of storing private keys in the database

- **Ciphertext is not safety:** Encryption keys that live beside the DB (env vars on app hosts) collapse to “secret in one place.”
- **Insider and backup risk:** Anyone with prod DB + secrets (or a bad backup policy) can exfiltrate or impersonate signers.
- **Recovery:** Lost wrapping keys = **irrecoverable user funds**; weak recovery flows = **support-led theft**.

### What is required before any custodial design is acceptable

| Requirement | Purpose |
|-------------|---------|
| **KMS (envelope encryption)** | Data keys never exist long-term in app memory or flat env; rotation and break-glass are defined. |
| **MPC or custody provider** (preferred) | Avoid holding a decryptable private key in your DB at all; vendor assumes part of the trust model. |
| **Signing isolation** | Minimal service that only signs **allowlisted** payouts; no interactive HTTP path to raw keys. |
| **Legal + product sign-off** | Custody, geography, and marketing (“invisible blockchain”) aligned. |

---

## 2. Future wallet architecture (options)

### A. Custodial with KMS (self-operated)

- **Pros:** Full control of UX; can automate payouts to addresses you control for users.
- **Cons:** You retain maximum legal/security liability; team must operate KMS, rotation, DR, and on-call for key incidents.

### B. Web3Auth (or similar)

- **Pros:** Can reduce password UX friction; can combine social login with non-custodial or MPC flows depending on product mode.
- **Cons:** **Not a drop-in “encrypted key in DB”**—must choose whether keys are user-held, MPC-sharded, or vendor-custodied; each has different contracts and UX.

### C. External wallet connection

- **Pros:** No key custody by the platform; aligns with self-custody and advanced users.
- **Cons:** **Breaks “blockchain invisible”** unless limited to optional “payout address” flows; sybil and support burden increase.

### Recommendation (non-binding)

- **Default path for “invisible” payouts:** **MPC / custody API** (or KMS-only if vendor not acceptable) + **snapshot payout destination** at batch finalization; **do not** store decryptable signing keys in application DB.
- **Optional later:** external wallet as **payout override** with clear “effective from batch N / time T” rules.

---

## 3. Security requirements (wallet + auth hardening)

| Area | Actionable minimum |
|------|---------------------|
| **Key management** | KMS or HSM-backed wrapping; no long-lived plaintext DEKs in repos or shared env; rotation runbooks. |
| **Signing isolation** | Separate deployable, least-privilege IAM, **allowlist** of programs/methods and **per-tx limits**; no signing from the general API tier. |
| **Audit logs** | Immutable-ish log stream: wallet created, address changed, signing requested (hash, amount, destination), success/failure, operator break-glass. |
| **Session / token hygiene** | Refresh rotation + reuse detection (partially deferred today); device/session inventory when abuse appears. |
| **Rate limits** | Auth endpoints and wallet mutation endpoints behind strict quotas + bot friction where needed. |

---

## 4. Auth improvements (future)

| Item | Notes |
|------|--------|
| **Google (OAuth2)** | Account linking (same email across providers), verified email policy, state/CSRF on callback. |
| **Web3Auth** | Only after wallet custody model is fixed; avoid parallel “custodial DB key + Web3Auth” without a single trust story. |
| **Device binding** | Bind refresh or session to device id / client attestation when threat model warrants it. |
| **Session management** | Server-side session table or opaque refresh families; admin revoke; “logout all devices.” |
| **Remove legacy header** | **`ENABLE_LEGACY_AUTH`** defaults **`false`**; keep **`false`** in production. Remove the `X-User-Id` code path once no clients need it. |

---

## 5. Migration plan (current → wallet-enabled)

1. **Freeze payout destination rules** — On batch finalization (or equivalent), **snapshot** `destination_wallet` / artist payout address so mid-batch wallet changes cannot redirect settled amounts.
2. **Introduce canonical wallet record** (or vendor wallet id) **linked to `User` / `Artist`**, with **`payout_wallet_address`** as denormalized or legacy field until cutover.
3. **Pilot signing service** — Off main API; fund with limited hot wallet; monitor logs and limits.
4. **Dual-write period** — New users get wallet id + address; existing artists keep `payout_wallet_address` until explicitly migrated.
5. **Cutover** — Stop accepting manual address edits without verification; require KMS/vendor path for new keys.
6. **Deprecate legacy auth** — Remove `X-User-Id` path after client JWT rollout is verified in logs (legacy is already **default-off** in `auth_config.py`).

**Ordering constraint:** (1) and (2) should precede any on-chain automation that spends real USDC at scale.

---

## 6. Risks

| Class | Risk |
|-------|------|
| **Legal (custody)** | Operating or effectively controlling user crypto may require **money transmitter** or equivalent registrations depending on jurisdiction and flow (especially if fiat on/off ramps appear). |
| **Security** | Custodial keys + single compromised worker = **mass drain**; weak refresh/session handling = **account takeover** → wrong payout address. |
| **UX complexity** | Export wallet, connect wallet, and “wrong network” errors **surface chain** to users; contradicts positioning unless tightly gated. |
| **Reconciliation** | On-chain truth vs ledger (`payout_settlements`, tx ids) must stay **idempotent** and **auditable** when wallets churn. |

---

## 7. Actionable checklist (when this file becomes active work)

- [ ] Choose: **KMS-only custodial** vs **MPC/vendor** vs **non-custodial** for v1 wallet.
- [ ] Write threat model + data classification for **keys, seeds, backups**.
- [ ] Implement **signing service** + **audit pipeline** before production keys.
- [ ] Legal review: custody, ToS, privacy (GDPR delete vs immutable chain).
- [ ] Product: **wallet change policy** vs in-flight batches; dashboard copy.
- [ ] Engineering: **remove legacy header auth** after metrics show zero deprecated auth warnings.

---

*Deferred by design: MVP auth is API JWT + cookies; wallet custody is intentionally out of scope until KMS/MPC and payout snapshot rules are in place.*
