# Auth — current implementation

## AUDIT SNAPSHOT (2026-04-29) — Roles and Access

## CURRENTLY IMPLEMENTED

- **Centralized frontend auth session manager**:
  - `AuthContext` is the app-level source of truth for `user`, `accessToken`, `isAuthenticated`, and `isLoading` (`initializing` alias remains for compatibility).
  - `forceLogout(reason?)` is exposed from `AuthContext` and is now the single invalid-session teardown path (clear memory token + local storage tokens + user state).
  - Non-React request code integrates through `frontend/lib/authSessionManager.ts`, which registers/unregisters the context-backed logout handler.
- **Reactive invalid-session handling**:
  - `apiFetch` interceptor calls `forceLogout(...)` on refresh failure/missing refreshed token/network exception.
  - `AuthContext.refreshSession()` and bootstrap error paths also call `forceLogout(...)`.
  - `/auth/me` unauthorized outcomes continue to collapse session to unauthenticated state through existing bootstrap/refresh flows.
- **Session-expired UX context propagation**:
  - `forceLogout(reason?)` now stores logout reason in session storage (`hm_logout_reason`) via `authSessionManager`.
  - `AuthGuard` consumes that reason and redirects protected-route unauthenticated users to `/login?reason=session_expired&returnUrl=...` for non-user-initiated logout reasons.
  - Interceptor now passes explicit reasons (`interceptor_refresh_failed_status`, `interceptor_refresh_missing_access_token`, `interceptor_refresh_exception`, `unauthorized`) into `forceLogout`.
- **Reactive protected-route redirect behavior**:
  - `AuthGuard` consumes centralized auth state (`isLoading`, `isAuthenticated`) and redirects unauthenticated sessions to `/login?returnUrl=...`.
  - `"/studio"` and `"/studio/*"` are protected at layout level (`frontend/app/studio/layout.tsx`), so route access is blocked whenever auth state becomes invalid.
- **Global frontend auth interceptor** (`frontend/lib/api.ts`):
  - `apiFetch()` now performs centralized 401 handling for all API calls except `/auth/refresh`.
  - On first 401, it runs a single-flight refresh (`POST /auth/refresh`, `credentials: "include"`), updates access token in both React memory bridge (`authHeaders.updateAccessToken`) and localStorage (`hm_access_token`), then retries the original request once.
  - Concurrent 401s share one in-flight refresh promise (`refreshPromise`) to prevent duplicate refresh calls.
  - On refresh failure/network error, access+refresh tokens are cleared from client storage and in-memory access token is nulled; response is propagated to callers (no forced UI redirect in interceptor).

- Authentication is JWT-based with refresh rotation and cookie support.
- Canonical registration role model supports:
  - `role=user`,
  - `role=artist` with `sub_role=artist|label`.
- Studio-sensitive routes are protected by ownership/context dependencies:
  - `require_artist_owner`,
  - context validation helpers,
  - participant checks for release approvals.
- User-scoped finance/comparison routes use `require_self_or_admin`.

## PARTIALLY IMPLEMENTED

- Route-protection strategy remains primarily auth-check based; stronger centralized route guard behavior is still pending.
- Session-expired UX is currently login-page scoped only (no global banner/modal framework yet).
- Additional UX refinements (custom per-reason copy variants and richer guidance) are still pending.
- Messaging is intentionally minimal and login-page scoped; no global notification/banner system exists yet.
- Frontend interceptor retries requests once after refresh and preserves existing `RequestInit`; this is safe for current JSON/FormData usage, but fully general replay guarantees for one-shot streaming request bodies are not explicitly implemented.
- Frontend enforces authentication broadly, but fine-grained role UX separation (user vs artist vs label) is still partial in route-level behavior.
- RBAC schema still includes string linkage compatibility paths, increasing long-term drift risk.

## NOT IMPLEMENTED

- Strictly separated frontend dashboard products per role are not fully realized:
  - `/studio` is the modern creator surface,
  - no modern React `/dashboard` equivalent for general user role separation.

## KNOWN ISSUES

- Interceptor intentionally does not perform route redirects/logout UI transitions; auth UX reconciliation remains component/state driven.
- Because protection is client-side in App Router components, users can observe a short guard loading state during hydration before redirect resolves.
- Session-expired reason is ephemeral (session storage + query param) and can be missing on direct `/login` navigation or manual query editing.
- Discovery admin analytics exposure risk:
  - `GET /discovery/admin/analytics` appears to lack explicit backend auth/admin guard in route definition.
- Mixed legacy and modern surfaces reduce clarity of effective role boundaries.

## ⚠️ SYSTEM INCONSISTENCIES

- Access control is strongest on backend ownership dependencies, while frontend route labels/nav can imply role specialization that is not always strictly enforced client-side.
- Product routing still mixes legacy role-era pages and studio-context architecture, making role behavior harder to reason about for operators.

## CURRENTLY IMPLEMENTED

### JWT access tokens

- **Library**: PyJWT (`jwt.encode` / `jwt.decode`).
- **Implementation**: `app/core/jwt_tokens.py`
- **Access token** (`create_access_token`): claims `sub` (user id as string), `iat`, `exp`, `typ="access"`; signed with `JWT_SECRET_KEY` (required length ≥ 32 via `require_jwt_secret()`); algorithm from `JWT_ALGORITHM` (default `HS256`).
- **Lifetime**: `ACCESS_TOKEN_EXPIRE` = **15 minutes** (`auth_config.py`).

### Refresh tokens

- **JWT refresh** (`create_refresh_token`): claims `sub`, `iat`, `exp`, `typ="refresh"`, `jti` (UUID string); returns `(token, expires_at)`.
- **Lifetime**: `REFRESH_TOKEN_EXPIRE` = **30 days** by default (`JWT_REFRESH_DAYS` env overrides day count).
- **Server-side row**: `RefreshToken` model (`refresh_tokens` table): `jti` unique, `user_id` FK, `expires_at`, `revoked_at`, `created_at`.
- **Issuance**: On `POST /auth/register` and `POST /auth/login`, a new `RefreshToken` row is inserted and JWTs returned.

### Refresh rotation

- **`POST /auth/refresh`** (`auth_routes.py`):
  - Accepts refresh token from JSON body `refresh_token` **or** httpOnly cookie (see below).
  - Decodes JWT → `jti`, `user_id`.
  - In a **single DB transaction** (`db.begin()`): loads refresh row (with `SELECT … FOR UPDATE` on **PostgreSQL** only), validates row + user, sets `revoked_at` on old row, inserts new `RefreshToken` row, mints new access token.
  - Returns new pair in JSON and sets cookie.

### HttpOnly cookie (browser)

- **`app/api/auth_cookies.py`**: cookie name `hm_refresh_token`, path `/auth`, `httponly=True`, `secure` from `AUTH_COOKIE_SECURE`, `samesite` = `none` if secure else `lax`.
- **Register/login/refresh** call `attach_refresh_cookie`; **logout** calls `clear_refresh_cookie`.

### Logout

- **`POST /auth/logout`**: resolves refresh from body or cookie; loads row via `load_refresh_token_row_for_revocation`; sets `revoked_at` if not already revoked; clears cookie; status **204**.

### Current user resolution

- **`HTTPBearer(auto_error=False)`** in `app/api/deps.py`.
- **`get_current_user`**: requires `Authorization: Bearer`; decodes with `decode_access_token`; loads `User` by `sub`; rejects missing/inactive user; supports impersonation tokens (see below).
- **`get_listening_user_id`**: used by streaming routes — **Bearer first**; if no bearer and `ENABLE_LEGACY_AUTH` truthy, accepts **`X-User-Id`** integer header (must exist in DB). Otherwise **401**.
- **`get_optional_user`**: for read-only routes (e.g. discovery); invalid/missing token → `None` without 401; still decodes impersonation and sets `request.state.impersonation_actor_id` when applicable.
- **`require_non_impersonation`**: if Bearer token decodes as impersonation type, raises **403** (used on sensitive routes).

### Registration / profile

- **`POST /auth/register`**: email normalization, token issuance, and role payload normalization with strict 400 validation on invalid combinations.
- **Password hashing stability guard**: bcrypt is pinned to a passlib-compatible version and registration rejects passwords over bcrypt's 72-byte limit with explicit 400 (`"Password too long"`), avoiding runtime hash failures.
- **Canonical role normalization**: internal persisted shape is now always `role ∈ {user, artist}` plus optional `sub_role`.
  - If `role` is present it is authoritative.
  - Else route falls back to legacy `role_type` (`user`, `artist`, `label`) for backward compatibility.
  - `role=artist` requires `sub_role` in `{artist, label}`.
  - `role=user` forbids `sub_role` (must be null).
- **Role-based registration behavior**:
  - `role=user` (or `role_type=user`): creates `User` + `UserProfile`, assigns RBAC role `user`, sets `onboarding_completed=false` and `onboarding_step=REGISTERED`.
  - `role=artist, sub_role=artist` (or legacy `role_type=artist`): creates owned `Artist`, assigns RBAC role `artist`, sets `onboarding_completed=false`.
  - `role=artist, sub_role=label` (or legacy `role_type=label`): creates owned `Artist` + owned `Label`, assigns RBAC role `artist`, sets `onboarding_completed=false`.
- **Register response shape**: includes token pair plus registration context (`user_id`, `email`, `roles`, `onboarding_completed`, `onboarding_step`, `sub_role`, optional `artist_id`/`label_id`).
- **`GET /auth/me` response** includes onboarding state (`onboarding_completed`, `onboarding_step`) and `sub_role`; onboarding step is canonicalized via `validate_onboarding_state(...)` before response serialization.
- **Onboarding state machine constants**: backend onboarding progression uses strict canonical states: `REGISTERED` → `PREFERENCES_SET` → `DISCOVERY_STARTED` → `COMPLETED`.
- **Onboarding write canonicalization**: onboarding completion writes uppercase `COMPLETED` only; model-level validator on `User.onboarding_step` rejects non-canonical values.
- **Magic-link preparation abstraction**: token issuance is centralized through `_issue_login_tokens_for_user(...)` to support future email-link login flow without changing route response contracts.
- **`POST /auth/login`**: email/password; inactive → 403; unverified email **does not** block login (comment in code).
- **`GET /auth/me`**: requires `get_current_user`; returns id, email, flags, `display_name` from profile, `roles` from `user_roles`, aggregated `permissions` from RBAC role-permission mappings, and optional `impersonation` block if actor id on request state.
- **RBAC permissions layer**: tables `roles`, `permissions`, `role_permissions` exist alongside `user_roles` (kept for compatibility). Permission checks can use `get_user_permissions(user_id)` and `has_permission(user, permission_name)` from `app/services/rbac_service.py`; `has_permission` can use preloaded permissions to avoid repeated queries in one request path.
- **Authorization helpers in use**: endpoint guards use `require_permission(permission_name)` for RBAC enforcement on selected admin/privileged routes; artist upload/write paths use dependency-based ownership checks.
- **Authorization helpers in use**: endpoint guards use `require_permission(permission_name)` for RBAC enforcement; artist write paths use dependency-based ownership checks (`require_artist_owner`, `require_song_owner`, `require_release_owner`) with optional RBAC permission gates on selected routes.
- **Release approvals participant-actor enforcement**: studio release approval endpoints enforce participant-level actor checks (`require_participant_actor` semantics): caller must own the target `artist_id`, and `(release_id, artist_id)` must exist in `release_participants`; this allows collaborators to approve/reject their own participation while preventing release owners from acting for other artists.
- **Legacy upload auth model**: deprecated `POST /artists/{artist_id}/songs` now relies on dependency-based ownership (`require_artist_owner`) only, matching canonical ownership-first upload authorization semantics.
- **Ownership source of truth**: auth-aware ownership checks use `get_artist_owner_id(artist)` backed solely by `owner_user_id` (no legacy `user_id` fallback).
- **Central write ownership dependencies** (`app/api/deps.py`):
  - `require_artist_owner(artist_id)` validates JWT user ownership for artist-scoped writes and returns the `Artist` row.
  - `require_song_owner(song_id)` and `require_release_owner(release_id)` enforce the same ownership contract for song/release mutation routes.
  - Shared check path `enforce_artist_ownership(...)` fails closed (403) when owner cannot be resolved and allows admin override via RBAC permissions (`admin_full_access` or `edit_any_artist`).
- **Central read access dependencies** (`app/api/deps.py`):
  - `require_artist_owner(artist_id)` also protects sensitive artist read surfaces (dashboard, analytics, payouts).
  - `require_self_or_admin(user_id)` protects user-scoped read routes (`/dashboard/{user_id}`, `/payout/{user_id}`, `/compare/{user_id}`), allowing only self access or admin override.
- **Studio context helpers** (`app/api/deps.py`):
  - `get_current_context(db, user)` resolves effective context from persisted `users.current_context_type/current_context_id`, falling back to `{type: "user", id: user.id}` when stored context is missing/invalid.
  - `validate_context_for_user_or_403(...)` and `is_context_allowed_for_user(...)` enforce fail-closed ownership validation for `user|artist|label` contexts.
  - Context ownership rules: `user` context id must equal authenticated `user.id`; `artist`/`label` context id must be owned by `owner_user_id`.
- **Studio context endpoints**:
  - `GET /studio/me` requires JWT and returns user identity + allowed contexts (`owned_artists`, `owned_labels`) + `current_context`.
  - `POST /studio/context` requires JWT, validates ownership server-side, persists the selected context, and returns updated `current_context`.
- **Prepared onboarding upload restriction**: helper `can_upload_song(user, artist, db)` is available for future enforcement; if `user.onboarding_completed=false`, upload is allowed only while artist has `<1` non-deleted song, otherwise unlimited.
- **Role assignment validation**: role writes through `create_user` now validate role names against `roles.name` via `assign_role_to_user` / `validate_role_exists`; unknown role assignments are rejected.
- **Invalid-role detection**: `/auth/me` keeps returning legacy `roles` values but triggers warning logs when a user has `user_roles.role` entries that do not exist in `roles.name`.

### Impersonation (development)

- **Enabled only when**: `is_dev_impersonation_enabled()` → `APP_ENV`/`ENV` ∈ `{development, dev}` **and** `ENABLE_DEV_IMPERSONATION` truthy (`auth_config.py`).
- **`POST /auth/dev/impersonate`**: body `target_user_id`; actor from `get_current_user`; mints **`create_impersonation_access_token`** (short-lived, `typ="access_impersonation"`, `actor` claim); rejects if already impersonating from state (**note**: state is set on Bearer resolution, not automatically on this mint — flow is “get new access token and use it”).
- **`/auth/me`**: includes `ImpersonationState` when `request.state.impersonation_actor_id` set from decoded access token.

### Legacy header auth

- **`ENABLE_LEGACY_AUTH`** env (default false): when true, `get_listening_user_id` accepts `X-User-Id` without Bearer; logs deprecation warning.

## PARTIALLY IMPLEMENTED

- **Strict single-flight refresh on SQLite**: code documents that without `FOR UPDATE`, SQLite dev DBs can race under concurrent refresh.
- **Artist ownership integrity gate**: Alembic `0021_validate_artist_owner_integrity` strictly blocks migration when any `owner_user_id` is null or mismatched (no automatic reassignment), and `0022_drop_legacy_artist_user_id` removes the legacy schema column afterward.
- **Studio context persistence rollout**: Alembic `0023_add_studio_context_to_users` adds nullable `users.current_context_type` and `users.current_context_id` for server-validated studio context storage.

## NOT IMPLEMENTED

- **OAuth2 third-party** (Google/GitHub, etc.): not present in `auth_routes` / deps reviewed.
- **Email verification flow**: `User.is_email_verified` exists; register path does not gate on verification (TODO comment references future withdrawal gating).

## KNOWN ISSUES

- **Authorization posture**: admin and privileged write routes use JWT identity + RBAC permissions (`admin_full_access`, etc.); no parallel shared-secret route authorization remains.
- **Cookie + CORS**: `main.py` documents `127.0.0.1` vs `localhost` mismatch for dev (middleware logs warning).
- **Post-reset auth false negatives (SQLite dev)**: after deleting/recreating `backend/dev.db` and reseeding while Uvicorn is already running, login checks can return transient `401 Invalid email or password` until the API process is restarted and reconnects to the fresh SQLite file.
- **RBAC linkage integrity gap**: `user_roles.role` is a free-form string (no FK to `roles`), so typos or renamed roles can still appear in `/auth/me.roles` while resolving to zero permissions.
- **RBAC naming drift risk**: role matching is string-based (`user_roles.role == roles.name`) rather than id-based; this is backward compatible but more fragile than a `role_id` FK design.
- **Owner integrity is strict**: owner-only enforcement denies when `owner_user_id` is missing, and migration `0021_validate_artist_owner_integrity` stops rollout until missing/mismatched rows are explicitly resolved.
- **Artist public profile routes remain public by design**: slug/id catalog reads (`/artist/{slug}`, `/album/{slug}`, `/track/{slug}`, `/artists/search`) are still public surfaces; only sensitive artist/user finance and analytics reads are ownership-gated.
