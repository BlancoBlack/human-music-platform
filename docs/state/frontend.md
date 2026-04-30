# Frontend — current implementation

### ADMIN PAYOUTS PAGE

- IMPLEMENTED
- New frontend admin route `"/admin/payouts"` exists at `frontend/app/admin/payouts/page.tsx`.
- Page consumes `GET /admin/payouts` via `fetchAdminPayouts(filters)` in `frontend/lib/api.ts`.
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
- `"/studio/catalog"` is data-backed:
  - catalog/tracks via `fetchStudioCatalog()` (`GET /studio/{artist_id}/catalog`)
  - full release grid via `fetchStudioReleases()` (`GET /studio/{artist_id}/releases`)
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
- No direct backend `fetch(...)` calls are present in active studio pages (`frontend/app/studio/*`).

## PARTIALLY IMPLEMENTED

- `"/studio"` mixes real data with scaffold UI:
  - profile image block is placeholder UI
  - bio section/edit button is placeholder UI text
- Studio feature surface is partially complete:
  - dashboard, catalog, approvals are implemented
  - analytics and payouts subpages are still placeholders
- Studio navigation includes both implemented and placeholder destinations in one menu.

## NOT IMPLEMENTED

- `"/studio/analytics"` does not implement production analytics views yet; page is placeholder text only.
- `"/studio/payouts"` does not implement production payout/settlement views yet; page is placeholder text only.
- `"/studio/release/[id]/edit"` does not implement edit tooling yet; page is an entry placeholder.
- `"/dashboard"` is not implemented in the App Router frontend.

## KNOWN ISSUES

- Studio secondary navigation exposes placeholder routes (`/studio/analytics`, `/studio/payouts`) as first-class tabs.
- `"/studio"` dashboard suggests editable profile sections but edit actions are not wired to mutation flows.
- Creator UX is split across modern studio routes and separate legacy-style creator pages (`/artist-analytics`, `/artist-catalog`, `/artist-upload`), which fragments the frontend surface.
- Frontend guards are primarily authentication-focused; strict role/ownership enforcement is mainly backend-driven.

## ⚠️ SYSTEM INCONSISTENCIES

- `"/studio"` root displays real insight and earnings data, while sibling tabs `"/studio/analytics"` and `"/studio/payouts"` are placeholders.
- Navigation presents analytics/payouts as available studio modules even though their pages are not implemented.
- Frontend contains both studio-era creator UX and legacy creator route surfaces, so there is no single consolidated creator frontend entrypoint.
