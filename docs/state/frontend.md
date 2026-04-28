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
- Single cover upload in `frontend/components/UploadWizard.tsx` uses `POST /releases/{release_id}/upload-cover` when `release_id` is available, with temporary compatibility fallback to `POST /songs/{song_id}/upload-cover` when missing.
- Album setup default release date in `frontend/components/album/AlbumReleaseSetupForm.tsx` is initialized to current time minus 30 minutes (`new Date(); setMinutes(getMinutes() - 30)`), preserving the existing `datetime-local` ISO formatting pipeline and improving recency consistency with single uploads.

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

## State Management Patterns (Hooks)

### Forbidden pattern

```ts
useEffect(() => {
  setLoading(true); // forbidden
  fetchData().then(...);
}, []);
```

Why this is forbidden:
- It adds avoidable extra renders by synchronously writing state as soon as the effect starts.
- It blurs React's dataflow model by using effects for state orchestration rather than side effects.
- It triggers `react-hooks/set-state-in-effect` lint violations.
- It increases risk of racey updates when async work resolves after navigation/unmount.

### Canonical patterns

#### 1) Event-driven state (inputs/search)

- Update immediate UI state in event handlers (`onChange`, button handlers).
- Keep effects for async side effects only (debounced search, fetch callbacks).

```ts
const [query, setQuery] = useState("");
const [results, setResults] = useState<Item[]>([]);
const [loading, setLoading] = useState(false);

const onChange = (value: string) => {
  setQuery(value);
  if (value.trim().length < 2) {
    setResults([]);
    setLoading(false);
  } else {
    setResults([]);
    setLoading(true);
  }
};

useEffect(() => {
  const q = query.trim();
  if (q.length < 2) return;
  let cancelled = false;
  void search(q)
    .then((items) => {
      if (!cancelled) setResults(items);
    })
    .catch(() => {
      if (!cancelled) setResults([]);
    })
    .finally(() => {
      if (!cancelled) setLoading(false);
    });
  return () => {
    cancelled = true;
  };
}, [query]);
```

#### 2) Fetch-driven state (pages)

- Initialize loading via `useState` once.
- Effect performs async work only.
- Write state only from async resolution (`then/catch/finally` or `await` path).
- Always include cancellation cleanup.

```ts
type State =
  | { kind: "loading" }
  | { kind: "ready"; data: Data }
  | { kind: "error"; message: string };

const [state, setState] = useState<State>({ kind: "loading" });

useEffect(() => {
  if (!slug.trim()) return;
  let cancelled = false;
  void fetchBySlug(slug)
    .then((data) => {
      if (!cancelled) setState({ kind: "ready", data });
    })
    .catch((e) => {
      if (!cancelled) {
        setState({
          kind: "error",
          message: e instanceof Error ? e.message : "Load failed.",
        });
      }
    });
  return () => {
    cancelled = true;
  };
}, [slug]);
```

### Cancellation pattern

```ts
let cancelled = false;

async function load() {
  const data = await fetchSomething();
  if (!cancelled) setState(data);
}

return () => {
  cancelled = true;
};
```

Why this is required:
- Prevents state writes on unmounted components.
- Avoids stale async responses overwriting newer UI state.
- Keeps page transitions safe under slow or flaky network conditions.

### Design principles

- Effects are for side effects, not synchronous state orchestration.
- No synchronous `setState` at effect start.
- UI state should be predictable from current inputs + async outcomes.

### Real Anti-Patterns (from this project)

- `frontend/components/UploadWizard.tsx`
  - What was wrong: search effects synchronously reset state (`setSearchResults`, `setSearchLoading`) at effect start.
  - Correct pattern: immediate reset/loading now happens in `onChange`; the effect only performs async search resolution.

- `frontend/app/discovery/page.tsx`
  - What was wrong: page fetch effect used synchronous `setLoading(true)` at top.
  - Correct pattern: loading is initialized in `useState`; effect performs fetch and only writes state in async callbacks.

- `frontend/app/album/[slug]/page.tsx`, `frontend/app/artist/[slug]/page.tsx`, `frontend/app/track/[slug]/page.tsx`
  - What was wrong: redundant `setState({ kind: "loading" })` at effect start despite loading already being initial state.
  - Correct pattern: remove redundant sync setter; keep state transitions in async success/error paths only.

### Lint Mental Rule (MUST FOLLOW)

```ts
useEffect(() => {
  setSomething(...); // almost always wrong
}, []);
```

If you ever write a synchronous `setState` at the top of a `useEffect`:

-> STOP

Ask:
- Can this be derived from initial state?
- Can this be triggered by a user action instead?
- Should this happen only after async resolution?

Remember:
- Effects are not for orchestrating state.
- Effects are for async side effects and subscriptions.

### Quick Checklist

Before writing a `useEffect`:
- Am I setting state synchronously? -> probably wrong.
- Can this be moved to `useState` initial value? -> preferred.
- Is this tied to user input? -> use an event handler.
- Is this async work? -> effect is fine.
- Do I need cancellation? -> usually yes.

## Expression Layer (NOT IMPLEMENTED)

- No illustration system exists yet.
- No motion system exists yet.
- Architecture is prepared via `docs/tech-debt/expression-layer.md` and inline frontend placeholders.
