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

- **`POST /auth/register`**: email normalization, password length 8–128, `create_user`, issues tokens; duplicate email → 400.
- **`POST /auth/login`**: email/password; inactive → 403; unverified email **does not** block login (comment in code).
- **`GET /auth/me`**: requires `get_current_user`; returns id, email, flags, `display_name` from profile, `roles` from `user_roles`, optional `impersonation` block if actor id on request state.

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

- **Security**: `ADMIN_KEY` and similar secrets for other routes are separate from JWT; operators must not reuse weak defaults in production.
- **Cookie + CORS**: `main.py` documents `127.0.0.1` vs `localhost` mismatch for dev (middleware logs warning).
