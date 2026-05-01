# Frontend — current implementation

### ADMIN PAYOUTS PAGE

- IMPLEMENTED
- New frontend admin route `"/admin/payouts"` exists at `frontend/app/admin/payouts/page.tsx`.
- Page consumes `GET /admin/payouts` via `fetchAdminPayouts(filters)` in `frontend/lib/api.ts`.
- Transaction links: the frontend does **not** build explorer URLs. `"/admin/payouts"` uses only `row.tx.explorer_url` from `GET /admin/payouts` for links; when `explorer_url` is null but a tx id exists, the table shows a truncated id (tooltip + copy control) with no link. `frontend/lib/explorer.ts` was removed; studio payouts likewise use only API `explorer_url`.
- MVP parity behaviors implemented:
  - filters: `status`, `artist_id`, `artist_name`, `limit`,
  - table columns: batch/users/artist/amount/status/wallet/tx/created/attempts/failure/actions,
  - settle action calling `POST /admin/settle-batch/{batch_id}`,
  - disabled retry action with Ledger V2 tooltip.
- Admin nav parity is wired between `"/admin/discovery"` and `"/admin/payouts"` via links in both admin pages.

### ADMIN ROLE GUARD

- IMPLEMENTED
- `"/admin/payouts"` checks `useAuth().user.roles` client-side and renders `Not authorized` when role `admin` is absent.
- Backend authorization remains the source-of-truth enforcement (`require_admin_user` on admin endpoints); frontend guard provides UX-layer protection.

### SETTLE SAFETY UX

- IMPLEMENTED (STRONG CONFIRMATION)
- Settle flow no longer uses `window.confirm`; it uses an explicit modal in `frontend/app/admin/payouts/page.tsx`.
- Modal requires exact case-sensitive text confirmation (`SETTLE`) in input `id="v9m7yk"` before execution is enabled.
- Modal displays payout-risk warning plus batch and amount context, prevents double-submit with loading/disabled controls, supports Escape-to-close, and keeps click-outside from ever confirming execution.
- Failed settle requests render inline modal error with retry path (modal remains open, confirm can be retried).
- **409** (batch lock): modal closes; the page shows the server `detail` in the main alert (see **UX HARDENING**).

### ADMIN ACTION LOGGING

- IMPLEMENTED
- Frontend API adds `fetchAdminActionLogs()` in `frontend/lib/api.ts`.
- `"/admin/payouts"` renders an **Admin Activity** section below the payouts table (see **ADMIN LOGS (ENRICHED)**).

### ADMIN LOGS (ENRICHED)

- IMPLEMENTED
- Activity table columns: **admin email**, **action**, **batch id**, **result summary** (retry: retried / success / failed from `metadata`; settle: confirmed / failed / skipped when present), **timestamp**.
- Retry success banner uses a two-line `Retry completed:` message with the same count format.

### DB LOCKING

- IMPLEMENTED (BACKEND)
- Admin UI continues to disable actions while `batch_status === 'processing'`; server-side locking is described in `docs/state/backend.md` (**DB LOCKING**).

### RETRY SYSTEM

- IMPLEMENTED
- `"/admin/payouts"` enables Retry when `batch_status === 'failed'` (ledger batch must be in failed state, not only a failed-looking row).
- Retry flow uses a dedicated confirmation modal requiring exact input `RETRY` before execution.
- Frontend calls `POST /admin/retry-batch/{batch_id}` through `postAdminRetryBatch(...)`, refetches payouts/activity on success, and shows success/error feedback.

### PROCESSING LOCK

- IMPLEMENTED
- Table status shows a **PROCESSING** label when `batch_status === 'processing'`, with a small inline spinner in the status cell.
- **Settle** and **Retry** are disabled while the batch is processing (server also enforces the lock).
- While any loaded row has `batch_status === 'processing'`, the page soft-refetches payouts and activity on a **backoff** schedule (**4s → 6s → 10s** max); the interval resets when no row is processing; the timer is cleared on unmount.

### UX HARDENING

- IMPLEMENTED
- `postAdminSettleBatch` / `postAdminRetryBatch` throw `ApiConflictError` on **409** with the API `detail` (default: batch processed by another admin); handlers close the modal and surface the message in the main alert (not raw JSON).
- Polling backoff and processing spinner are documented under **PROCESSING LOCK**.
- Broader multi-admin collaboration gaps: `docs/tech-debt/admin.md` (**MULTI-ADMIN COLLABORATION (FUTURE)**).

### RETRY RESULT SUMMARY

- IMPLEMENTED
- `postAdminRetryBatch(...)` parses the JSON body `{ retried, success, failed }` and surfaces counts in the success banner (`Retry completed:` + `N retried / …`).

### ADMIN PAYOUTS UI

- LEGACY REMOVED
- Frontend no longer depends on `"/admin/payouts-ui"` and uses API-driven admin payouts + activity surfaces.

## CURRENTLY IMPLEMENTED

### App Structure

- Frontend uses Next.js App Router under `frontend/app`.
- `"/"` exists as a static landing shell in `frontend/app/page.tsx`.
- Studio routes currently present:
  - `"/studio"` (`frontend/app/studio/page.tsx`)
  - `"/studio/catalog"` (`frontend/app/studio/catalog/page.tsx`)
  - `"/studio/analytics"` (`frontend/app/studio/analytics/page.tsx`)
  - `"/studio/payouts"` (`frontend/app/studio/payouts/page.tsx`)
  - `"/studio/pending-approvals"` (`frontend/app/studio/pending-approvals/page.tsx`)
  - `"/studio/releases/[id]"` (`frontend/app/studio/releases/[id]/page.tsx`)
  - `"/studio/release/[id]/edit"` (`frontend/app/studio/release/[id]/edit/page.tsx`)
- No App Router page exists for `"/dashboard"` (`frontend/app/dashboard` is absent).

### Studio System

- `"/studio"` renders a dashboard that loads real backend data:
  - context from `fetchStudioMe()` (`GET /studio/me`)
  - payout/dashboard stats from `fetchStudioArtistDashboard()` (`GET /studio/{artist_id}/dashboard`)
  - insight story from `fetchArtistInsights()` (`GET /artist/{artist_id}/insights`)
- `"/studio"` renders loading/error/no-artist states and real earnings fields (`total`, `paid`, `accrued`, `failed_settlement`, `pending`, `last_payouts`, `spotify_total`, `difference`).
- `"/studio/payouts"` is implemented and data-backed:
  - payload via `fetchStudioArtistPayouts()` (`GET /studio/{artist_id}/payouts`)
  - renders payout method card (radio selection UI + editable wallet input + save action), summary, and payout history table.
  - save flow calls `postStudioArtistPayoutMethod()` (`POST /artist/{artist_id}/payout-method`) with loading/success/error feedback and post-save refresh.
  - wallet input is enabled only when `crypto` is selected; selecting `bank` disables wallet input.
  - bank detail content is never rendered in UI; only `bank_configured` state is shown.
  - summary copy clarifies payout lifecycle terminology:
    - `Paid out to you`,
    - `Generated, pending payout`,
    - `Currently being processed` (shown only when pending amount > 0),
    with short helper text to reduce confusion between generated vs transferred amounts.
  - final UX polish includes refined wording (`Number of payments`, `Last payment date`), improved summary spacing, and payout history **Tx ID** (when provided): middle-truncated display (prefix/suffix via ellipsis, responsive to column width via `ResizeObserver`), native `title` tooltip with the full id, explorer link uses `explorer_url` from the API only (`target="_blank"`, no client-side URL construction), click on the link also copies the full id to the clipboard, plus a small inline copy control; em-dash when `tx_id` is missing (no tooltip/click); if `tx_id` is present but `explorer_url` is absent, the id is shown without a link (copy still works).
- `"/studio/catalog"` is data-backed:
  - catalog/tracks via `fetchStudioCatalog()` (`GET /studio/{artist_id}/catalog`)
  - full release grid via `fetchStudioReleases()` (`GET /studio/{artist_id}/releases`)
- `"/studio/analytics"` is implemented and data-backed:
  - **Artist selector** at top: lists every artist from `fetchStudioMe().allowed_contexts.artists` (`GET /studio/me`); shown even when only one artist; initial selection prefers current artist context when present and allowed, otherwise first listed artist; changing the selection refetches analytics for that artist.
  - loads a single payload via `fetchStudioArtistAnalytics()` (`GET /studio/{artist_id}/analytics?range=...`) only — no legacy `/artist-analytics` or per-metric `/artist/{id}/streams` calls
  - range selector: `last_day`, `last_week`, `last_30_days` (default), `last_3_months`
  - **Streams chart**: Recharts `LineChart` inside `ResponsiveContainer` (tooltips enabled); x = bucket label (`date` key), y = `streams`
  - tables for top songs (title, streams, % of total over returned rows) and top fans (username, total streams, favorite song title + streams)
  - loading, empty (per section), and error states; optional “Updating analytics…” while refetching
- `"/studio/releases/[id]"` is data-backed and interactive:
  - detail via `fetchStudioReleaseDetail()` (`GET /studio/releases/{release_id}`)
  - actions via `postStudioReleaseApprove()` and `postStudioReleaseReject()`

### Components

- Studio layout shell is reusable:
  - `StudioLayout` (`frontend/components/studio/StudioLayout.tsx`)
  - `StudioSecondaryNavbar` (`frontend/components/studio/StudioSecondaryNavbar.tsx`)
- Reusable studio/catalog components in active use:
  - `ReleaseGridTile` (`frontend/components/catalog/ReleaseGridTile.tsx`)
  - `StudioApprovalStatusBadge` (`frontend/components/studio/StudioApprovalStatusBadge.tsx`)
- Shared participant shaping is reused in release approvals:
  - `buildParticipantViewModel()` (`frontend/lib/participantViewModel.ts`)

### Data Layer

- Frontend API wrapper is `apiFetch()` in `frontend/lib/api.ts`.
- Studio data calls are defined in `frontend/lib/api.ts` and used by studio pages/components.
- `apiFetch()` uses browser `fetch` internally and applies auth headers/cookies centrally.
- `apiFetch()` now includes a global auth interceptor:
  - first 401 (except `/auth/refresh`) triggers single-flight refresh (`POST /auth/refresh`),
  - successful refresh updates in-memory/localStorage access token,
  - original request is retried once with fresh auth headers.
- Frontend has a centralized auth-session bridge:
  - `frontend/lib/authSessionManager.ts` connects non-React request/interceptor code to `AuthContext` logout behavior.
  - `AuthContext.forceLogout(reason?)` is registered as the global invalid-session teardown handler.
- No direct backend `fetch(...)` calls are present in active studio pages (`frontend/app/studio/*`).

### Route Protection

- `"/studio"` and all nested `"/studio/*"` routes are now layout-protected via `frontend/app/studio/layout.tsx` wrapped in `AuthGuard`.
- `AuthGuard` is reactive to centralized auth state from `AuthContext` (`isLoading`, `isAuthenticated`):
  - while loading: shows guard loading state (no premature redirect),
  - when unauthenticated: redirects to `/login?returnUrl=...`.
- Guard re-evaluates automatically when auth state changes (including interceptor-triggered `forceLogout`), so invalidated sessions inside protected routes redirect without manual page logic.
- Session-expired UX is implemented in the login route:
  - `AuthGuard` adds `reason=session_expired` to login redirect when logout came from invalid session reasons.
  - Login page renders friendly copy (`"Your session has expired"`, `"For security reasons, please log in again."`) when `reason=session_expired`.
  - Login success preserves `returnUrl` when present (validated internal path), otherwise falls back to onboarding/discovery routing.

## PARTIALLY IMPLEMENTED

- Route protection remains component-driven; no stronger centralized route-guard policy was added in this session.
- Current session-expired UX is intentionally minimal (login-page inline message + redirect context); no modal/banner/session page system.
- Additional UX refinement opportunities remain (copy variants, optional inline recovery hints).
- Session-expired UX is currently limited to login-page inline messaging; broader cross-page guidance remains pending.
- `"/studio"` mixes real data with scaffold UI:
  - profile image block is placeholder UI
  - bio section/edit button is placeholder UI text
- Studio feature surface is partially complete:
  - dashboard, catalog, analytics, approvals are implemented
  - payouts is implemented and data-backed
- Studio navigation is fully implemented for listed tabs; remaining gaps are route-specific (e.g. release edit placeholder).

## NOT IMPLEMENTED

- `"/studio/release/[id]/edit"` does not implement edit tooling yet; page is an entry placeholder.
- `"/dashboard"` is not implemented in the App Router frontend.

## KNOWN ISSUES

- Global auth interceptor does not attempt replay-specific handling for non-replayable request body streams; current app calls are JSON/FormData-oriented and unaffected.
- Client-side guard can still briefly render loading placeholders during hydration/bootstrapping before redirect decisions complete.
- Session-expired reason context can be absent on direct `/login` visits or manual URL edits (login gracefully falls back to standard sign-in UI).
- Studio secondary navigation includes a data-backed analytics route (`/studio/analytics`).
- `"/studio"` dashboard suggests editable profile sections but edit actions are not wired to mutation flows.
- Creator UX is split across modern studio routes and separate legacy-style creator pages (`/artist-catalog`, `/artist-upload`); `/artist-analytics` redirects to `/studio/analytics`.
- Frontend guards are primarily authentication-focused; strict role/ownership enforcement is mainly backend-driven.

## ⚠️ SYSTEM INCONSISTENCIES

- `"/studio"` root and `"/studio/payouts"` are data-backed, while sibling `"/studio/analytics"` remains placeholder.
- Navigation presents analytics as available even though the analytics page is not yet implemented.
- Frontend contains both studio-era creator UX and legacy creator route surfaces, so there is no single consolidated creator frontend entrypoint.
