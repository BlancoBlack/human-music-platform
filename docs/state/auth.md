# Auth — current implementation

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
- **`GET /auth/me` response** now includes onboarding state (`onboarding_completed`, `onboarding_step`) and `sub_role`.
- **Onboarding state machine constants**: backend onboarding progression uses strict states: `REGISTERED` → `PREFERENCES_SET` → `DISCOVERY_STARTED` → `COMPLETED`.
- **Magic-link preparation abstraction**: token issuance is centralized through `_issue_login_tokens_for_user(...)` to support future email-link login flow without changing route response contracts.
- **`POST /auth/login`**: email/password; inactive → 403; unverified email **does not** block login (comment in code).
- **`GET /auth/me`**: requires `get_current_user`; returns id, email, flags, `display_name` from profile, `roles` from `user_roles`, aggregated `permissions` from RBAC role-permission mappings, and optional `impersonation` block if actor id on request state.
- **RBAC permissions layer**: tables `roles`, `permissions`, `role_permissions` exist alongside `user_roles` (kept for compatibility). Permission checks can use `get_user_permissions(user_id)` and `has_permission(user, permission_name)` from `app/services/rbac_service.py`; `has_permission` can use preloaded permissions to avoid repeated queries in one request path.
- **Authorization helpers in use**: endpoint guards use `require_permission(permission_name)` for RBAC enforcement; artist write paths can combine RBAC with ownership checks via `can_edit_artist`.
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

## NOT IMPLEMENTED

- **OAuth2 third-party** (Google/GitHub, etc.): not present in `auth_routes` / deps reviewed.
- **Email verification flow**: `User.is_email_verified` exists; register path does not gate on verification (TODO comment references future withdrawal gating).

## KNOWN ISSUES

- **Authorization posture**: admin and privileged write routes use JWT identity + RBAC permissions (`admin_full_access`, etc.); no parallel shared-secret route authorization remains.
- **Cookie + CORS**: `main.py` documents `127.0.0.1` vs `localhost` mismatch for dev (middleware logs warning).
- **RBAC linkage integrity gap**: `user_roles.role` is a free-form string (no FK to `roles`), so typos or renamed roles can still appear in `/auth/me.roles` while resolving to zero permissions.
- **RBAC naming drift risk**: role matching is string-based (`user_roles.role == roles.name`) rather than id-based; this is backward compatible but more fragile than a `role_id` FK design.
