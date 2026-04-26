# Frontend — current implementation

## CURRENTLY IMPLEMENTED

- Client auth state is managed by `frontend/context/AuthContext.tsx`.
- Login/register call backend auth endpoints via `frontend/lib/auth.ts`; after credentials succeed, **`auth.applyTokens`** persists tokens and performs **exactly one** `GET /auth/me` (explicit Bearer). `AuthContext.login` / `AuthContext.register` return that `UserMe` so `login`/`register` pages do not call `refreshUser()` again (avoids duplicate `/auth/me` after sign-in).
- Cookie refresh (`refreshSession`) reuses **`auth.applyTokens`** after a successful `POST /auth/refresh` so refresh and login paths share the same `/auth/me` contract.
- Authenticated API calls use `frontend/lib/api.ts` and attach Bearer headers via `frontend/lib/authHeaders.ts`.
- Listening/session API calls are centralized in `frontend/lib/listening.ts` and use `apiFetch`.
- Auth bootstrap reads token from localStorage, validates via `/auth/me`, and falls back to `/auth/refresh` when needed.
- `OnboardingRouteGuard` blocks non-public routes until auth is ready; unauthenticated users hitting protected routes are handled via `AuthGuard` (redirect to `/login`).
- Post-onboarding UX is explicit and deterministic: `frontend/app/onboarding/page.tsx` navigates to `frontend/app/user-register-complete/page.tsx`, and that page CTA always navigates to `"/discovery?from=onboarding"` (no API calls on the milestone page).
- `frontend/lib/onboarding.ts` `resolveOnboardingRoute`: only incomplete states (`REGISTERED`, `PREFERENCES_SET`) return `"/onboarding"`; `DISCOVERY_STARTED` and `COMPLETED` return `null` — no global forced destination to `/player`.
- Onboarding routing enforcement is scoped to onboarding-critical paths only: `/`, `/onboarding`, `/user-register-complete`. `useOnboardingRedirect` is disabled for all other routes (including `/discovery`, slug pages, upload routes, and `/player`), eliminating global onboarding redirect side-effects.
- Onboarding route matching in `OnboardingRouteGuard` uses a Set-based lookup (`ONBOARDING_ROUTES.has(pathname)`) for robust constant-time checks; behavior remains identical to the scoped guard model.
- Discovery is the primary post-onboarding destination and global fallback route; `frontend/app/discovery/page.tsx` treats `?from=onboarding` for banner copy and “Play now” emphasis without autoplay.
- **Slug-shaped public pages** (Next.js App Router): `frontend/app/artist/[slug]/page.tsx`, `frontend/app/album/[slug]/page.tsx`, and `frontend/app/track/[slug]/page.tsx` fetch public entity JSON via slug-based API helpers (e.g. `fetchTrackBySlug` in `frontend/lib/api.ts`); when the API returns a canonical slug that differs from the URL segment, pages align the visible route with `router.replace` (backend may also emit **`301`** redirects on the raw HTTP slug endpoints).
- **Post-login navigation**: `frontend/app/login/page.tsx` uses `router.replace(resolveOnboardingRoute(user) ?? "/discovery")` so users without an enforced onboarding target land on **Discovery**, not `/player`.
- **Post-register navigation**: `frontend/app/register/page.tsx` uses `router.replace(resolveOnboardingRoute(user) ?? "/onboarding")` to preserve the explicit registration -> onboarding contract.
- **Player routing model**: `/player` is fully excluded from onboarding-guard scope and is never used as an onboarding/default fallback destination (`frontend/app/player/page.tsx` falls back to `"/discovery"` after explicit play-completion transitions).

## PARTIALLY IMPLEMENTED

- None for this document scope.

## NOT IMPLEMENTED

- None for this document scope.

## NETWORK CALL AUDIT

- `frontend/lib/listening.ts`: uses `apiFetch` for `/stream/start-session`, `/stream/checkpoint`, `/stream` (authenticated path).
- `frontend/app/onboarding/page.tsx`: uses `submitOnboardingPreferences` from `frontend/lib/api.ts` (apiFetch-backed).
- `frontend/app/discovery/page.tsx`: uses `fetchDiscoveryHome` from `frontend/lib/api.ts` (apiFetch-backed).
- `frontend/app/register/page.tsx`: uses `AuthContext.register` -> `frontend/lib/auth.ts`.
- `frontend/app/user-register-complete/page.tsx`: no backend API calls (navigation only).

Raw fetch calls previously found:

- `frontend/lib/auth.ts` for `/auth/register`, `/auth/login`, `/auth/me`, `/auth/dev/impersonate`, `/auth/refresh`, `/auth/logout`.
- `frontend/app/page.tsx` for `/balance`, `/stream`.

Root causes:

- Legacy direct fetch usage in auth helper and home page bypassed the shared request client contract.
- Mixed network usage made auth handling inconsistent and harder to reason about.
- UI timing race existed where non-public routes could be interactive before a confirmed auth session, allowing playback/listening actions to fire without a valid Bearer token.

## AUTH LIFECYCLE

1. App mounts `AuthProvider`.
2. Bootstrap starts (`initializing=true`, `authReady=false`).
3. Access token is read synchronously from localStorage.
4. If token exists, `/auth/me` validates session.
5. If invalid and refresh token exists, `/auth/refresh` is attempted.
6. Context settles (`initializing=false`, `authReady=true`) with either:
   - authenticated user + access token, or
   - logged-out state.
7. Non-public routes render only after auth is ready; unauth users are redirected to login.

Final guarantee:

- Authenticated API calls run with Authorization header whenever token exists in memory or localStorage.
- Playback/listening start-session retries once on 401 for bootstrap/login-transition timing races.

## KNOWN ISSUES

- None for onboarding guard scope.

## GUARDRAIL

- No raw `fetch()` for backend API calls.
- All frontend API requests must go through `apiFetch` in `frontend/lib/api.ts`.
- Exception policy: none currently.

## Contract alignment after refactor

- `/player` is removed from onboarding route resolution contract (`resolveOnboardingRoute` returns `"/onboarding"` or `null` only).
- Onboarding routing model is now: incomplete users route to `/onboarding`; otherwise no forced onboarding redirect target.

## Expression Layer (NOT IMPLEMENTED)

- No illustration system exists yet.
- No motion system exists yet.
- Architecture is prepared via `docs/tech-debt/expression-layer.md` and inline frontend placeholders.
