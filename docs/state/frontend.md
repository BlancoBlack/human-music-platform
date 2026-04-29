# Frontend — current implementation

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
