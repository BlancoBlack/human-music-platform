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
`UploadWizard` and related flows may need clearer states, error mapping, and progress for large masters.

**Why it matters**  
Upload is the supply side of the catalog; friction reduces content.

**Current behavior**  
Functional MVP; see existing components and API error shapes (`wav_file_too_large`, etc.).

**Proposed solution**  
UX audit: chunked upload if needed, clearer validation messages, resume failed uploads.

**Priority:** MEDIUM  

**When to address:** **Post-MVP** as catalog grows.

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
