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
- Listener **library** routes:
  - **`"/library/playlists"`** (`frontend/app/library/playlists/page.tsx`) lists the signed-in user’s playlists via TanStack Query **`queryKey: ["playlists"]`** and **`fetchPlaylistSummaries()`** (`GET /playlists`), reusing the same cache as **`PlaylistModal`**. Backend orders **“Liked Songs”** first for each user (created at registration). Grid **`PlaylistCover`** uses **`thumbnails={playlist.thumbnail_urls}`**; **`PlaylistCover`** resolves relative API paths with **`NEXT_PUBLIC_API_BASE`** (same rules as playlist detail header). Empty **`thumbnail_urls`** keeps the gradient placeholder. Grid cards use hover shadow plus **`PlaylistCover`** zoom **inside** an **`overflow-hidden`** clip (no **`translate-y`** / no layout shift on the title); links go to **`/library/playlists/[id]`**.
  - **`"/library/playlists/[id]"`** (`frontend/app/library/playlists/[id]/page.tsx`) — **playlist detail**:
    - Loads **`fetchPlaylistDetail(id)`** (`GET /playlists/{id}`) with **`queryKey: ["playlist", id]`**. Header **`PlaylistCover`** uses truthy **`cover_urls`** (paths resolved inside **`PlaylistCover`**). Each row shows **`cover_url`** as **`${API_BASE}${cover_url}`** when present (~**48–56px** thumb, **`No cover`** fallback); **playable** rows use **`group/play`** hover (index hides, play triangle); rows without **`audio_url`** stay non-clickable for play, reduced opacity, lock icon, **`title="Track not available"`**, no row hover play highlight. Meta: **`Your playlist`** when **`owner_user_id`** matches the signed-in user; **Public** badge when **`is_public`**. **Play** uses **`displayTracks`** order; **`useAudioPlayer().playTrack`** sends **`playbackSource: { source_type: "playlist", source_id: "<id>" }`**; **`continuePlaybackSource`** for autoplay/next/prev (see **`AudioPlayerProvider`**). Stable **`key={song_id}`**; active row emerald emphasis; **`scrollIntoView({ behavior: "smooth", block: "nearest" })`** when the playing **`song_id`** changes.
    - **Owner drag & drop (`@dnd-kit`):** reorder is **owner-only**; non-owners see no handle and no **`DndContext`**. **Handle-only** drag (six-dot **grip**, **`group/row`** hover reveal); **`PointerSensor`** activation distance **6px** so scrolling is unlikely to start a drag.
    - **`DragOverlay`:** floating **visual-only** preview (**~`scale-[1.03]`**, **`shadow-lg`**, **`opacity-95`**, **`pointer-events-none`**); no play affordance and **no** **`SongActions`**. The sortable source row uses **`opacity: 0`** + **`pointer-events: none`** while dragging to avoid a double-row illusion.
    - **Drop indicator:** thin **emerald** bar (**`bg-emerald-500`**, slight glow) absolutely positioned **above** the row currently under the pointer (**`dragOverSongId`**), only when **`dragActiveSongId !== dragOverSongId`**.
    - **Motion:** **`CSS.Transform.toString(transform)`** on sortable items; **`useSortable`** **`transition: { duration: 150, easing: 'ease-out' }`** plus **`opacity 150ms ease-out`** on the row; **`DragOverlay`** **`dropAnimation`** ~**180ms** **`ease-out`**.
    - **Reorder API:** **`putPlaylistReorder(playlistId, orderedSongIds)`** → **`PUT /playlists/{id}/reorder`** with **`{ ordered_song_ids }`** (same contract as backend); **success:** **`await queryClient.refetchQueries({ queryKey: ["playlist", playlistId] })`** then optional player queue sync (below); **errors:** **`invalidateQueries`** + **`showError`** (see **`ToastContext`**).
    - **Player queue sync after reorder:** When **`getPlaybackSource()`** matches **`{ source_type: "playlist", source_id: String(playlistId) }`**, **`replaceQueuePreservingPlayback(newQueue)`** runs after refetch ( **`newQueue`** from refreshed **`tracks`** sorted by **`position`**, same **`toPlayable`** mapping). Updates **`queue`** / **`currentIndex`** / **`currentTrack`** reference **only** — **no** **`finalizeSession`**, **no** **`postStartSession`**, **no** **`audio.src`** change — so playback position and audio do **not** restart. Discovery or other **`playbackSource`** values skip sync (**no-op**).
    - **Consistency (verified):** **`SongActions`** unchanged (**`stopPropagation`** wrapper). Manual playlist play, **`continuePlaybackSource`** autoplay/next/prev, and discovery **`playbackSource`** semantics unchanged aside from the guarded playlist reorder sync.
  Empty list shows **`No playlists yet`**; unauthenticated users see sign-in copy with **`returnUrl=/library/playlists`** (detail **`returnUrl`** includes the playlist id).

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

### Discovery page & global player (listener)

- **`"/discovery"`** (`frontend/app/discovery/page.tsx`): each track row includes **`SongActions`** — like (optimistic via TanStack Query `queryKey: ["likes"]`, `useLikes()` hook) and add-to-playlist (`PlaylistModal` loads **`GET /playlists`** on open, adds via **`POST /playlists/{id}/tracks`**; can **`POST /playlists`** with **`{ title }`** to create inline then auto-add the track — see **`PlaylistModal`**). Anonymous users see disabled actions with sign-in hint semantics (`title` / `aria-label`).
- **`GlobalPlayerBar`** (`frontend/components/audio/GlobalPlayerBar.tsx`): shows **`SongActions`** for the current track id when something is playing.
- **`AudioPlayerProvider`** (`frontend/components/audio/AudioPlayerProvider.tsx`): registers a **`window` `keydown`** listener — **Space** toggles play/pause when a **`currentTrack`** is loaded (`preventDefault` to avoid scrolling); **`isTyping(event.target)`** skips handling when focus is inside **`input`**, **`textarea`**, or **`contentEditable`**, so typed spaces (e.g. playlist name in **`PlaylistModal`**) are not captured by the player; if **`event.defaultPrevented`** (e.g. row **`role="button"`** handlers that already consume Space), the shortcut does not run. Exposes **`suppressNextClicks(ms?)`** (default **~250ms**) and **`isActivationClickSuppressed()`**: **`PlaylistModal`** calls **`suppressNextClicks`** immediately before every close path; discovery and library playlist **track row `onClick`** bail out when **`isActivationClickSuppressed()`** so a post-dismiss stray **`click`** does not start playback (**keyboard** **`onKeyDown`** unchanged). **Queue sync:** **`getPlaybackSource()`** reads the internal listening attribution ref; **`replaceQueuePreservingPlayback(nextQueue)`** updates **`queue`**, **`currentIndex`**, and aligns **`currentTrack`** to the row in **`nextQueue`** with the **same `id`** while leaving the **`<audio>`** element and listening session untouched — used so playlist reorder does not leave next/prev/autoplay on a stale order (**`/library/playlists/[id]`** reorder **`onSuccess`**).
- **Toast (minimal, no library)**: `ToastProvider` + `useToast()` in `frontend/context/ToastContext.tsx`; mounted in **`AppProviders`** between **`AuthProvider`** and **`QueryProvider`**. API: **`showSuccess(message, opts?)`** (optional **`action: { label, href }`** renders an inline link CTA; longer ~**4.5s** dismiss when an action is present), **`showError(message)`** — fixed bottom stack, small rounded shadow panel, fade + slight slide-in via CSS + `requestAnimationFrame`, default auto-dismiss ~**2s**. At most **2** toasts visible: enqueueing a third drops the **oldest** (slice to trailing two).
- **Like loading UX**: `useLikes()` exposes `loadingSongIds` (`Set<number>`). While a song’s like/unlike request is in flight, **`SongActions`** disables the heart, sets `aria-busy`, and shows a small spinner; optimistic cache updates and rollback on failure are unchanged. On mutation failure after rollback, **`showError("Could not update like")`** runs.
- **Playlist modal feedback**: **`PlaylistModal`** supports choosing an existing playlist **or** **inline create**: empty state shows copy plus **Create playlist**; when the user already has playlists, **+ Create new playlist** appears below the list — both reveal a **playlist name** field and **Confirm** (small spinner on Confirm while the create+add sequence runs; Confirm disabled when the name is empty or any submit is in flight). Inline title field uses **`autoFocus`** when mounted (no **`requestAnimationFrame`** focus); while list/create requests are in flight it uses **`readOnly`** plus reduced-opacity / **`cursor-wait`** styling so the control **stays focusable** (not **`disabled`**). The **`role="dialog"`** panel uses **`onKeyDown`** to **`stopPropagation`** for **Space** so stray bubbling does not reach global handlers. The fixed overlay closes only when **`onClick`** **`target === currentTarget`** (direct backdrop hit, not bubbled); **`onMouseDown`** **`preventDefault`** on that same backdrop guard absorbs the press so a close does not produce a trailing **click** on the page underneath. All closes use **`closeModal()`** → **`suppressNextClicks(250)`** then parent **`onClose`**; **Escape** on the dialog panel also **`closeModal()`**. Flow: **`createPlaylist(title)`** → **`POST /playlists`** → **`addTrackToPlaylist(newId, songId)`** → **`invalidateQueries(["playlists"])`** → **`showSuccess(`Added to ${title}`, { action: { label: "View", href: `/library/playlists/${id}` } })`** and close (same toast as picking an existing playlist). **Create** failure: **`showError`** with server/detail or generic copy, modal stays open, **input value preserved**. **Add** failure after a successful create: error toast, modal stays open, playlists refetched (new playlist visible in list); inline form collapses and clears. Picking an existing playlist unchanged: success toast + close; duplicate/other errors unchanged. While any row pick or create confirm is in flight, the modal disables double-submit across list + create controls.
- **Providers**: `AuthProvider` → **`ToastProvider`** → `QueryProvider` → … in `frontend/components/AppProviders.tsx`. API helpers for likes/playlists live in `frontend/lib/api.ts` (`fetchLikedSongIds`, `postLikeSong`, `deleteLikeSong`, `fetchPlaylistSummaries`, **`createPlaylist`** (`POST /playlists`, body **`{ title }`**), `addTrackToPlaylist`, `fetchPlaylistDetail`, **`putPlaylistReorder`** (`PUT /playlists/{id}/reorder`, body **`{ ordered_song_ids }`**)).

### Components

- Studio layout shell is reusable:
  - `StudioLayout` (`frontend/components/studio/StudioLayout.tsx`)
  - `StudioSecondaryNavbar` (`frontend/components/studio/StudioSecondaryNavbar.tsx`)
- Reusable studio/catalog components in active use:
  - `ReleaseGridTile` (`frontend/components/catalog/ReleaseGridTile.tsx`)
  - `StudioApprovalStatusBadge` (`frontend/components/studio/StudioApprovalStatusBadge.tsx`)
- Listener playlist UI:
  - `PlaylistCover` (`frontend/components/PlaylistCover.tsx`) — square **`rounded-xl`** frame; **`thumbnails`** are **deduped by URL** (first occurrence order), first **4** unique kept; if fewer than four unique URLs, the grid **repeats** those URLs to fill four cells; otherwise violet-neutral gradient placeholder with centered icon in a subtle elevated disc (**`shadow-inner`** / ring).
  - `PlaylistModal` (`frontend/components/PlaylistModal.tsx`) — add-to-playlist modal (same **`["playlists"]`** query as the library page); inline **create + auto-add** after **`POST /playlists`**; success toast names the playlist + **View** action.
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

- **Playlist reorder — queue sync edge cases:** **`replaceQueuePreservingPlayback`** is a **no-op** if the playing track’s **`song_id`** is missing from the refetched **`tracks`** list (unexpected data mismatch), if **`nextQueue`** is empty, or if nothing is playing with an **`audioUrl`**. Next/prev/autoplay then reflect whichever **`queue`** state last applied — same as before sync attempt (no forced playback change).
- **Playlist reorder — timing:** Sync runs immediately after **`refetchQueries`** for **`["playlist", playlistId]`** resolves; slow networks add a short window before UI + player queue both match the server.
- **Playlist detail — index vs order before refetch:** The index column renders API **`position`** from each enriched track row. Immediately after a successful drag, **`items`** reflects the new order while **`position`** fields may still match the **previous** **`GET /playlists/{id}`** response until the query refetch completes; labels then align with the server.
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
