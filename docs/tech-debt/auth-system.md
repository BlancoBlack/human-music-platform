# Auth, session, and wallet — tech debt (consolidated)

**Scope:** JWT access + refresh (DB `jti`, **rotation** on `POST /auth/refresh`), httpOnly refresh cookie (`hm_refresh_token`, path `/auth`), Next.js `AuthContext` + Bearer on API calls, **deprecated** optional **`X-User-Id`** for listening (opt-in via `ENABLE_LEGACY_AUTH=true` — default **false**). **Per-user custodial wallets are not implemented**; payouts use **`Artist.payout_wallet_address`**. Wallet-only product/architecture notes stay in [auth-and-wallet.md](./auth-and-wallet.md).

---

## 0. Identity model (authoritative)

- **`Authorization: Bearer <access_jwt>`** is the **only** way the API identifies the caller for **`GET /auth/me`**, **`get_current_user`**, and other Bearer-protected routes. There is **no** cookie-based fallback for `/auth/me`.
- **httpOnly `hm_refresh_token` cookie** (path **`/auth`**) is used **only** for **`POST /auth/refresh`** (rotate session + set new cookie), **`POST /auth/logout`** (revoke + clear cookie), and responses from **`POST /auth/register`** / **`POST /auth/login`** (set cookie). It is **not** a second identity source for **`/auth/me`**.
- **Access JWT** is short-lived. It is either a normal **access** token (`typ=access`) or a **dev impersonation** access token (`typ=access_impersonation`); see **Dev impersonation** below.

### Dev impersonation

- **`POST /auth/dev/impersonate`** is **disabled unless** `APP_ENV`/`ENV` is **`development`** or **`dev`** **and** **`ENABLE_DEV_IMPERSONATION=true`**. In production, keep impersonation **off** (unset or `false`) and do **not** use `development`/`dev` for `APP_ENV` if you rely on this gate.
- Returns a **short-lived access JWT only** — **no** new refresh token and **no** refresh-cookie rotation for impersonation.
- **`GET /auth/me`** reflects impersonation when that access JWT is sent as **Bearer** (`impersonation` in JSON). Exiting uses **`POST /auth/refresh`** with the existing httpOnly cookie to mint a normal access token (`AuthContext.exitImpersonation` → `refreshSession()`).

---

## 1. Refresh token system — current behavior and limitations

**Implemented today**

- **One-time rotation:** Valid refresh JWT maps to a DB row; on success the row gets `revoked_at`, a new `RefreshToken` row is inserted, and a new refresh JWT is issued. Reuse of an old refresh token returns 401.
- **Backend atomicity:** Rotation runs in a single SQLAlchemy transaction (`Session.begin()`); on PostgreSQL the refresh row is selected with **`FOR UPDATE`**. SQLite dev has no real row-level `FOR UPDATE` semantics for concurrency.
- **Frontend single-flight (per tab):** `AuthContext` uses a module-level `refreshPromise` so concurrent `refreshSession()` calls in the same tab (e.g. React Strict Mode, multiple mounts) share one `refreshToken()` request.

**Limitations**

- **No cross-tab coordination:** Each browser tab has its own JS heap. `refreshPromise` does not span tabs. Two tabs can each call refresh close together → two server rotations from two valid cookies is not prevented by the frontend; one request wins, the other typically fails → **logout or 401 in the losing tab(s)**.

### SQLite limitation (IMPORTANT)

The default **dev** app DB is **SQLite** (`DATABASE_URL` in `app/core/database.py`).

- **No true row-level locking** for refresh rotation the way PostgreSQL does with **`SELECT … FOR UPDATE`**.
- **Concurrent refresh** requests (multiple tabs, workers, or retries) can **race** at the DB layer: one transaction may succeed, another may fail or observe inconsistent timing **unpredictably** compared to Postgres.

**Impact:** acceptable for **local development**; **not** a safe choice for **production** refresh rotation under real concurrency or load.

**Future directions**

- **`BroadcastChannel`:** Broadcast “session refreshed” / new access hint so other tabs avoid redundant refresh or re-fetch user once.
- **`localStorage` mutex:** Lease key + TTL so only one tab runs refresh at a time (brittle but simple).
- **Shared Worker:** Single owner of refresh + token handoff to tabs (heavier operational cost).

---

## 2. Refresh security (deferred)

**Not implemented**

- No **token family** (`family_id`) linking rotations to a logical session.
- No **reuse detection** policy beyond “revoked token fails”: presenting a **previously revoked** refresh token does not automatically revoke all other sessions or families.
- No **device binding** (refresh tied to fingerprint / attestation).
- No **global “logout all sessions”** API for password change or compromise response.

**Future**

- Add `family_id` (or equivalent) on `refresh_tokens`; propagate on rotation.
- On suspicious reuse (e.g. revoked `jti` presented again): revoke family or all user refresh rows; alert; force re-login.
- **`POST /auth/logout-all`** (authenticated): revoke all refresh rows for the user; clear cookie; optional access blocklist until next login.

---

## 3. CSRF and cookie model

**Current**

- **httpOnly** refresh cookie (`hm_refresh_token`), path **`/auth`** (only sent to auth routes under that path prefix, depending on browser path matching).
- **`SameSite`:** `Lax` when `AUTH_COOKIE_SECURE` is off (typical local HTTP); `None` when cookie is **Secure** (HTTPS). Implemented in `auth_cookies.py` (`_cookie_samesite()`).
- **CORS:** Explicit `allow_origins` with **`allow_credentials=True`**; default / merged dev origin **`http://localhost:3000`** (`main.py`). Mixed **`127.0.0.1` vs `localhost`** breaks credentialed flows; API logs a warning if `Origin` contains `127.0.0.1`.

**Limitations**

- **No dedicated CSRF token** for `POST /auth/refresh`: the browser can send the refresh cookie on a cross-site request in scenarios where `SameSite` does not block it (e.g. `SameSite=None` production misconfiguration or historical clients). This is a known class of risk for cookie-based refresh.
- Refresh remains **cookie-first** (JSON body still supported for non-browser clients).

**Future**

- Double-submit CSRF token (header or body) or custom header required on refresh.
- Stricter **SameSite** policy where same-site BFF or same registrable domain allows it.
- **BFF / same-origin proxy** so refresh is same-site to the SPA.

---

## 4. Email system (partial)

**Current**

- Register/login require **email** at the API; **`create_user()`** rejects **`None`** email and normalizes/validates format in the app layer.
- DB column **`users.email`** remains **nullable** for legacy SQLite rows.
- **`is_email_verified`** defaults **false**; login is **not** blocked for unverified users (MVP).
- **No** outbound email (no verification mail, no reset mail).

### Email validation limitations

Validation in **`normalize_registration_email`** (**`/auth/register`** and **`/auth/login`**) is **intentionally minimal**:

- Allows **short** domains that still satisfy the string rules (e.g. addresses like **`a@b.c`** if they pass length and `local` / `domain` / **`.`** checks).
- **No MX** (or other DNS) checks — deliverability is not verified.
- **No** disposable-email detection or blocklists.

**Rationale:** reduce false rejections at sign-up; good enough for MVP.

**Future (validation hardening):** stricter **RFC-aligned** parsing where product needs it, optional disposable-domain lists, optional **domain reputation** or third-party verification (watch latency and false positives).

**Limitations** (flows and product)

- No verification, resend, or expiry tokens.
- No password reset or email change flows.
- Product still needs explicit gates before sensitive actions (payout / payout-address changes are documented as future economics concerns in code comments).

**Future** (flows and product)

- Verification tokens (hashed), rate-limited send/resend, idempotent verify endpoint.
- Password reset with generic response to reduce enumeration; invalidate refresh rows on reset.
- Email change: verify new address, then switch primary + audit.

---

## 5. User creation consistency

**Current**

- **`app.services.user_service.create_user()`** is the single path for new auth-backed users: normalized email, hashed password, **`User`** + **`UserProfile`** + default **`UserRole`** (`listener`). Used from **`/auth/register`**, seed scripts, and tests that need full rows.

**Limitations**

- DB still allows **`NULL` email**; SQL or one-off scripts can insert users **without** going through `create_user()`.
- Legacy **`username`** remains on **`User`**; seeds may pass **`username=`** keyword-only for backward compatibility.

**Future**

- Migration: backfill then **`NOT NULL`** on `email` where product allows.
- Stricter DB constraints and/or triggers for rows that must be “auth” users only.

---

## 6. Legacy auth (`X-User-Id`) — deprecated

**Current**

- **`ENABLE_LEGACY_AUTH`** defaults **`false`** (`auth_config.py`). When set **`true`**, listening/stream resolution accepts **`X-User-Id`** without Bearer (`deps.py`). **Not recommended for production.**
- Each use logs a **deprecation** style message (`DEPRECATED AUTH METHOD USED: X-User-Id header …`).
- Frontend listening helper can still send **`X-User-Id`** from **`NEXT_PUBLIC_LISTENING_USER_ID`** for dev playback (`listening.ts`) only if legacy is enabled.

**Risks**

- With legacy enabled, any client that can set headers can impersonate a numeric user id (**header spoofing**).

**Plan**

- Track volume via logs / metrics when legacy is temporarily on.
- Keep **`ENABLE_LEGACY_AUTH=false`** in production; remove header path from **`get_listening_user_id`** once no callers need it.

---

## 7. Frontend session system

**Current**

- **Single-flight refresh** per tab (`refreshPromise` in `AuthContext.tsx`).
- **Bootstrap:** `useEffect` runs **`refreshSession()`** on mount; **`initializing`** gates UI until complete.
- **User cache:** `user` and access token come from **`AuthContext`**; **`syncUserFromMe()`** centralizes **`GET /auth/me`** after token changes; **`refreshUser()`** for explicit re-fetch after profile-changing actions.

**Limitations**

- No **cross-tab** session sync; refresh or logout in one tab does not update others automatically.
- **Logout** in one tab does not clear session state in other tabs until they hit an error or remount.
- Multi-tab refresh race remains (see §1).

**Future**

- **`BroadcastChannel`** (or `storage` events) for “logged out”, “tokens refreshed”, or “re-fetch me”.
- Optional shared session layer; global logout propagation.

---

## 8. Wallet system (deferred)

**Reality**

- **End-user custodial wallets are not implemented** in this codebase. Listening and balances are user-centric; **on-chain payout** flows use **`Artist.payout_wallet_address`** (and settlement rows), not per-listener chain wallets.

**Why deferred**

- Custodial or app-held keys imply **key management**, **security**, and **legal/compliance** surface area that the current MVP deliberately avoids.

**Future (high level)**

- **KMS**-backed signing, **MPC** or custody **vendor**, or non-custodial user-controlled keys—plus a **wallet abstraction** layer if multiple models coexist. Detail stays in [auth-and-wallet.md](./auth-and-wallet.md) when product commits.

---

## 9. Blockchain / payout risks

**Current behavior (accurate)**

- **`PayoutSettlement.destination_wallet`** is set from the **current** **`Artist.payout_wallet_address`** when the **settlement worker** builds or updates that settlement row (see `settlement_worker.py`: read artist → write `destination_wallet` on the row). That **snapshots the address onto the settlement record** for that processing attempt.

**Remaining risk**

- **`Artist.payout_wallet_address`** remains **mutable** at any time. If it changes **between** payout batch lifecycle phases (e.g. after amounts are fixed but before settlement reads the artist), funds can be directed to a different address than an operator assumed when reviewing the batch. Risk severity depends on how long the window is and whether UI/policy freeze addresses.

**Future**

- Snapshot **payout destination** (or hash) at **batch seal / snapshot build** and validate settlement against it.
- Immutability rules or audit when **`payout_wallet_address`** changes during an open batch.

---

## 10. Production readiness checklist

### MUST before production

- [x] **`ENABLE_LEGACY_AUTH`** defaults **`false`**; confirm production env does **not** set it to `true` (header-spoofing risk).
- [ ] **Rate limiting** on **`/auth/login`**, **`/auth/register`**, **`/auth/refresh`** (and related abuse surfaces).
- [ ] **`JWT_SECRET_KEY`** (and refresh signing secret if distinct) strong, rotated with a runbook.
- [ ] **Monitor** refresh failures / 401 spikes (rotation conflicts, theft attempts).
- [ ] **Migrate to PostgreSQL** (or another DB with real row locks) **before production** — do not run concurrent refresh rotation on SQLite under load.
- [ ] **Confirm `SELECT … FOR UPDATE`** on the refresh-token row path works in staging/prod (same dialect as production; regression-test refresh under parallel requests).
- [ ] **Consistent domains:** HTTPS, **`AUTH_COOKIE_SECURE`**, **`CORS_ORIGINS`** explicit, no accidental **`127.0.0.1`** / **`localhost`** mix in prod.
- [ ] **CSRF posture** for cookie refresh decided (§3) and implemented if `SameSite=None` or cross-site SPA.

### CAN wait (post-MVP / scale)

- [ ] Email verification, password reset, email change.
- [ ] Token family + reuse-driven revoke-all; **`logout-all`** endpoint and UI.
- [ ] CSRF token / BFF hardening beyond baseline SameSite.
- [ ] Multi-tab **`BroadcastChannel`** session sync.
- [ ] Wallet / custody (§8) and stricter payout address lifecycle (§9).
- [ ] Device binding / refresh attestation.

---

*Update this file when auth, refresh, cookies, listening identity, or settlement identity rules change. Wallet product deferrals: [auth-and-wallet.md](./auth-and-wallet.md).*
