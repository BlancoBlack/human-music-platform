# Reorder signals — Tech debt & follow-ups

Type: TECH_DEBT  
Focus: `playlist_reorder_events` ingest and **`load_reorder_signal_by_song`** runtime aggregation for discovery. Current behavior is documented in **`/docs/state/backend.md`** and **`/docs/state/discovery.md`**.

---

## Implemented (baseline)

- Append-only events on successful reorder; **`playlist_updated_at`** post-mutation snapshot.
- Discovery: **14-day** hard window, join **`playlists`** (non-deleted, owner matches event user), per-event **`min(delta_position, 5)`** via portable SQL, **×0.4** for private **`Liked Songs`** title (same string as **`like_service.LIKED_SONGS_PLAYLIST_TITLE`**), **`min(sum, 20)`** + **`log1p`** in Python; optional **`HM_DEBUG_REORDER_SIGNAL`** logs top contributing **`playlist_id`** per song (no API exposure).

---

## 1. Replace title-based “Liked Songs” detection

**Issue:** Liked canonical playlist is inferred from **`title` + `is_public`** — renames, i18n, or duplicate titles can misclassify.

**Direction:** Add a stable **`playlist_kind`** (or enum) column / constant distinct from user-editable title; set on create for system playlists; migrate existing liked rows.

**When:** Before scaling personalization that depends on liked vs manual semantics.

---

## 2. Soft decay (exponential or half-life)

**Issue:** Hard **14-day** cutoff is simple but has a cliff; stale intent drops to zero abruptly.

**Direction:** Weight each event by **`exp(-λ * age_days)`** (or linear ramp) inside the aggregate, still one query if expressed in SQL.

**When:** Product wants smoother “memory” or A/B shows cliff hurts quality.

---

## 3. Anti-spam / rate limiting

**Issue:** Clamp + short window + cap + **`log1p`** reduce abuse; determined reorder loops can still saturate per-song cap.

**Direction:** Per-playlist or per-user daily caps; session-level dedupe; or down-rank bursts in application logic.

**When:** Abuse or synthetic engagement appears in telemetry.

---

## 4. Materialized `playlist_reorder_stats` (optional)

**Issue:** Each discovery request runs grouped aggregates over events for up to **~500** candidate song ids.

**Direction:** If read cost dominates, maintain rolling aggregates (by user/song/window) via periodic job or trigger — **not** required at current scale.

**When:** Profiling shows reorder query material share of **`pool_ms`** under production load.

---

## 5. Explainability in product (not logs)

**Issue:** Debug map is env-gated logs only.

**Direction:** Internal admin or dev-only JSON if operators need live inspection without log access.

**When:** Ops asks for repeatable visibility beyond logging.
