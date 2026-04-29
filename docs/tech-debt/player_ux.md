Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/streaming.md
Last Verified: 2026-04-29

# Tech debt: Advanced player UX (Frontend)

Deferred **presentation and discovery** features for the global audio player. Complements [player.md](./player.md) (timing, unload, ingestion-adjacent behavior) and [ux.md](./ux.md) (broader surfaces).

---

## Advanced Player UX (Queue UI, Waveform, Up Next)

**Description**  
The global player is **functionally complete** for MVP: persistent bar across navigation, queue with next/previous, autoplay on track end, catalog and song-page playback. It still lacks **advanced UX** common on modern streaming products (Spotify, SoundCloud): visible queue, waveform-style progress, and explicit “up next” affordances.

### Missing features

#### 1. Queue visualization (“Up Next” list)

- Users cannot see **upcoming** tracks in order.
- **Playback order** is opaque even though `queue` and `currentIndex` exist in client state.

#### 2. Waveform / interactive progress bar

- Progress is a **linear bar** only; no representation of **audio energy** or structure.
- Seeking is click-to-position but not **fine-grained** or visually rich compared to waveform UIs.

#### 3. “Up next” preview

- No compact **next track** title (or art) in the chrome.
- No **transition awareness** (e.g. what autoplays after the current song).

**Why it matters**  
- Improves **engagement** and trust (“I know what’s playing next”).  
- Makes the product feel like a **real streaming** experience, not only a minimal transport bar.  
- Reduces friction when **browsing** while listening.  
- Aligns with **industry-standard** expectations for queue + progress UX.

**Current behavior**  
- Global bar shows: **title**, cover (when provided), **play/pause**, **prev/next**, **seekable progress**.  
- **Queue** exists in `AudioPlayerProvider` but is **not surfaced** in the UI beyond prev/next.

**Proposed solution**

#### Queue UI

- **Expandable panel** or **side drawer** listing queue items from `currentIndex` onward (or full list with current highlighted).  
- **Highlight** the active track; optional drag-reorder is out of scope until product asks for it.

#### Waveform

- **Precompute** waveform peaks during **ingestion** (backend or batch job) and expose via API, **or**  
- **Client-side** / cached lightweight generation for MVP visualization.  
- Replace or augment the flat bar with a **waveform** (read-only first; interactive seek second).

#### Up next

- Show **next track title** (and optional thumbnail) in the bar when `currentIndex < queue.length - 1`.  
- Optional **subtle transition** cue when autoplay advances (non-blocking, no mandatory animation).

**Priority:** LOW (post-MVP UX polish)

**When to address**  
- After **core streaming stability** (sessions, finalize, autoplay, cross-page player) is validated in real use.  
- **Before** broad **public release** or **beta** if competitive UX is a launch criterion.

---

*Split from “player” concerns: this file is polish and discovery; [player.md](./player.md) remains timing, unload, and policy-heavy client behavior.*

## Related State
- /docs/state/streaming.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/streaming.md
