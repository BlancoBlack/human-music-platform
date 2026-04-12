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
`UploadWizard` and related flows may need clearer states, error mapping, and progress for large masters. Separately, the **metadata model** for supply-side catalog is still MVP-scoped relative to a full rights-aware platform.

**Why it matters**  
Upload is the supply side of the catalog; friction reduces content. Missing **credits, splits, and rights** fields block label-grade payouts and discovery features later.

**Current behavior**  
- **UX:** Functional MVP; see existing components and API error shapes (`wav_file_too_large`, etc.).  
- **Metadata captured today (representative):** song title; **featured artists** (by artist id—no percentage split on collaborators); **credits** with roles: musician, mix engineer, mastering engineer, producer, studio (name + role per row).  
- **Not modeled in upload/API today:** songwriter and label as credit roles; **royalty % splits** for collaborators and non-artist entities; **ownership / rights / publishers**; **genre, subgenre, mood, audio characteristics** (beyond duration from WAV).

**Proposed solution**  
- **UX:** Chunked upload if needed, clearer validation messages, resume failed uploads.  
- **Data model (pairs with [backend.md](./backend.md) identifiers + credit-role evolution):** extend schema and wizard steps for additional credit types, split tables, rights parties—behind explicit product scope.

**Priority:** MEDIUM  

**When to address:** **Post-MVP** as catalog grows; schema work sooner if external partners require splits/ISRC before UX polish.

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
