Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/frontend.md
Last Verified: 2026-04-29

# Tech debt: UX

User-visible surfaces adjacent to listening, uploads, and discovery. Does not change API contracts by itself.

---

## Player progress bar (scrubber + time)

**Description**  
The global bar shows title and play/pause/stop only—no `currentTime` / duration UI or seek.

**Why it matters**  
Expected baseline for music apps; improves trust and control.

**Current behavior**  
Hidden `<audio>`; no progress binding to UI.

**Proposed solution**  
Subscribe to `timeupdate` + `durationchange`; read-only bar for MVP seekless; optional seek later (policy: seek might affect checkpoint `position_seconds` semantics).

**Priority:** MEDIUM  

**When to address:** **Post-MVP** polish sprint.

---

## Better error UI (not only console logs)

**Description**  
Ingestion failures (finalize after 410, play failure, network) log to `console.error` but do not show toasts, banners, or inline player error states.

**Why it matters**  
Users cannot self-recover or report issues; support lacks visible signals.

**Current behavior**  
Console-only for critical ingestion paths; catalog may show generic play errors.

**Proposed solution**  
- Small `PlayerError` state in context: `{ code?, message, recoverable }`.  
- Toast or bar message + “Retry” where safe.  
- Map known codes: `session_expired`, `invalid_sequence_start`, rate limits.

**Priority:** HIGH  

**When to address:** **Before broader beta**; pairs with **player** hardening.

---

## Upload flow improvements

**Description**  
`UploadWizard` serves as both **create** and **edit** flow. Large-master UX (chunked upload, resume) is still MVP-scoped.

**Why it matters**  
Upload is the supply side of the catalog; friction reduces content.

**Current behavior (implemented)**  
- **Create mode** (`POST /songs`, authenticated + artist-ownership enforced): title, primary artist, featured artists (by artist id), credits (musician, mix engineer, mastering engineer, producer, studio, songwriter, sound designer — name + role per row), genre, subgenre, moods (up to 3), country/city location.  
- **Edit mode** (wizard with `song_id` param, `PATCH /songs/{id}`): loads and hydrates all metadata. Songs with `upload_status === "ready"` lock title, featured artists, and royalty splits; genre, subgenre, credits, moods, location remain editable.  
- **Royalty splits** (`PUT /songs/{id}/splits`): percentage splits across artists; `SongArtistSplit` table; locked once song is ready.  
- **Soft delete** (`DELETE /songs/{id}`): sets `deleted_at`; song disappears from catalog, discovery, and analytics surfaces.  
- **Ownership model**: ownership is transitioning to `artists.owner_user_id` (legacy `artists.user_id` may still appear in older code paths); mutating flows increasingly combine RBAC permissions with ownership checks.

**Remaining gaps**  
- Chunked upload for large masters (>100 MB WAV).  
- Rights / publishers / label-as-credit-role not yet modeled.  
- Media upload endpoints (`upload-audio`, `upload-cover`) lack authentication (ownership not enforced at route layer).

**Priority:** MEDIUM  

**When to address:** Media auth before broader beta; chunked upload and rights model post-MVP.

---

## Release scheduling architecture pointer

**Description**  
Scheduled publishing now uses an MVP polling auto-publish loop (`scheduled` → `published`) in backend worker infrastructure.

**Where to find technical details**  
See backend tech debt entry: **"Release Auto-Publish Scheduler (Polling-based)"** in [backend.md](./backend.md).

**Why this pointer exists**  
UX behavior for future-dated releases depends on this backend mechanism and its known limitations (polling delay, single-instance assumptions).

---

## Artist catalog enhancements

**Description**  
Catalog lists songs with play integration; could add sorting, filters, search-in-page, “now playing” highlight, accessibility.

**Why it matters**  
Discovery and artist satisfaction; reduces support questions.

**Current behavior**  
Basic list + play on playable rows.

**Proposed solution**  
Pagination, status filters, link to full track detail page, keyboard nav.

**Priority:** LOW  

**When to address:** Iterative **post-MVP** improvements.

---

## Home / balance demo page vs real product IA

**Description**  
Root `app/page.tsx` still resembles a demo (balance fetch, stub stream button) rather than a cohesive entry to catalog or player.

**Why it matters**  
First impression and navigation clarity.

**Current behavior**  
Legacy demo patterns mixed with newer artist flows.

**Proposed solution**  
Information architecture pass: landing → discover / library → player; deprecate dead buttons.

**Priority:** LOW  

**When to address:** **Pre-launch** marketing site split or app shell redesign.

## Related State
- /docs/state/frontend.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/frontend.md
