Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/streaming.md
Last Verified: 2026-04-29

# Tech debt: Global audio player

Client: `AudioPlayerProvider`, engaged time via `performance.now()` segments, checkpoints ~30s, finalize on end / track change / stop / unload lifecycle.

---

## `navigator.sendBeacon` for unload finalize (blocked by custom headers)

**Description**  
`sendBeacon` is ideal for fire-and-forget unload requests but does not support arbitrary headers (e.g. `X-User-Id`) in a portable way. The app uses `fetch` with `keepalive: true` for unload finalization instead.

**Why it matters**  
`keepalive` improves odds the request completes on tab close but is still browser-dependent; beacons would be simpler if auth allowed query/cookie.

**Current behavior**  
`pagehide` / `beforeunload` → `finalizeCurrentIfNeeded({ keepalive: true })` → `postFinalize` with `keepalive: true`.

**Proposed solution**  
- **Short term:** Keep `keepalive` + document limits (payload size ~64KB, etc.).  
- **Long term:** Cookie-based or query-token auth for a dedicated `POST /stream/finalize-beacon` (narrow scope, CSRF-safe) so `sendBeacon` can be used without custom headers.

**Priority:** HIGH  

**When to address:** **Post-MVP** hardening; revisit if unload loss metrics are high.

---

## Engaged time accuracy: exclude buffering / stall

**Description**  
Engaged seconds accumulate wall-clock time while the `<audio>` element is in a playing state, including time before audible output (buffering) while not paused.

**Why it matters**  
Antifraud and fairness: “listen” may be defined as audible progress, not decoder wait time.

**Current behavior**  
`play` / `pause` events drive `performance.now()` accumulation; no distinction for `waiting` / `stalled` vs actual playback.

**Proposed solution**  
- Gate accumulation on `timeupdate` deltas (with seek detection) or on `playing` event vs `waiting`.  
- Cap segment growth per wall-clock second.  
- Align with backend threshold semantics in `validate_listen`.

**Priority:** MEDIUM (HIGH if antifraud requires audible-only time)  

**When to address:** **Before payouts v2** or when fraud review demands it.

---

## Background tab policy: pause vs keep counting

**Description**  
Browsers throttle timers; audio may still play in background. Policy is implicit: time keeps accruing if playback continues and pause is not fired.

**Why it matters**  
Product may want “background play doesn’t count” or “only foreground counts” for royalties.

**Current behavior**  
No `document.visibilityState` handling; rely on actual play/pause and audio state.

**Proposed solution**  
- Decide product rule.  
- If background should not count: pause engage clock when `document.hidden` OR pause audio per policy.  
- Document edge cases (mobile, PIP).

**Priority:** MEDIUM  

**When to address:** **Post-MVP**; align with **backend policy** and artist terms.

---

## Persistent player state across reloads

**Description**  
Beyond ingestion session recovery (see [ingestion.md](./ingestion.md)), the **UI** state (current track, position, playing) does not survive reload.

**Why it matters**  
UX continuity; pairs with session recovery for a coherent “resume listening” story.

**Current behavior**  
Full remount loses track unless user navigates within SPA without reload.

**Proposed solution**  
- `sessionStorage` or `localStorage` for last track id + optional position (with TTL).  
- Rehydrate after consent/privacy review; coordinate with session API.

**Priority:** HIGH (paired with CRITICAL ingestion recovery)  

**When to address:** Same phase as **session recovery** (post-MVP, pre-production).

---

## Double `play()` retry is a narrow fix

**Description**  
Only one automatic `play()` retry exists after `start-session`; other failure classes (CORS, autoplay policy) may need user gesture or UI prompts.

**Why it matters**  
Reduces orphan sessions but doesn’t solve all autoplay restrictions.

**Current behavior**  
Two attempts then abandon session + log.

**Proposed solution**  
Surface “Tap to play” when `NotAllowedError`; keep session until user confirms or cancels.

**Priority:** MEDIUM  

**When to address:** **Post-MVP** UX pass.

## Related State
- /docs/state/streaming.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/streaming.md
