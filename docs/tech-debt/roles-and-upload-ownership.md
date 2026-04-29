Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/auth.md
Last Verified: 2026-04-29

# Roles and upload ownership

**Status:** RBAC permissions are implemented and active on selected routes; ownership enforcement is implemented for artist upload via `can_edit_artist` and owner linkage. Label/roster-style multi-artist authorization is still future work.  
**Purpose:** Document current RBAC + ownership behavior and future role/roster evolution in the upload pipeline.

---

## 1. Current ownership model (implemented)

Artist-level ownership now uses `artists.owner_user_id` as the primary ownership field (legacy `artists.user_id` still exists for backward compatibility in older paths):

- **One authenticated user maps to one or more artists** through owner linkage.
- The upload wizard runs under a **fixed artist context** (`fixedArtistId` on `UploadWizard`).
- **Server-side enforcement** on mutating song endpoints:
  - `POST /songs` — requires `artist.user_id == current_user.id` (403 otherwise).
  - `PATCH /songs/{id}` — ownership via `assert_user_owns_song` (song -> artist -> `user_id`).
  - `DELETE /songs/{id}` — same ownership check (soft delete).
  - `PUT /songs/{id}/splits` — same ownership check.
- **Current enforcement:** `POST /artists/{artist_id}/songs` requires RBAC permission `upload_music` and ownership-aware authorization (`can_edit_artist`).
- **Known gap:** media endpoints (`POST /songs/{song_id}/upload-audio`, `POST /songs/{song_id}/upload-cover`) are still tracked separately and should be reviewed under the same RBAC + ownership model.

This model is **adequate for artist-only** journeys but **does not scale** once we introduce:

- **Labels** uploading on behalf of multiple roster artists,
- **Admins** acting across catalogs,
- Or any **multi-tenant ownership** boundary.

Until roles exist, treat the upload pipeline as **single-artist-context only** at the product layer.

---

## 2. Planned roles (future system)

Definitions below describe **intent**, not current implementation.

### Artist

- **Owns** their catalog (songs, releases, metadata).
- **Uploads** their own music.
- **Must not** select another primary artist during upload; context is always "self".

### Label

- **Manages** multiple artists (roster).
- **May upload** music **on behalf of** a chosen artist.
- **Requires** an explicit **artist selection** in the upload flow (which artist this track is for).
- Backend must validate that the selected artist is **in scope** for that label (relationship + permission).

### User (fan)

- **Consumes** content (listen, follow, playlists as a listener).
- **No upload** permissions in the default model.

### Curator

- **Curates** discovery surfaces (playlists, editorial lists, etc.).
- **No upload** permissions unless the product explicitly extends scope later.

### Admin

- **Full** operational access as defined by product policy.
- **May override** ownership or context where legally and product-wise allowed (audited, rare).

---

## 3. Upload pipeline implications

### 3.1 Current behavior (artist-only mental model)

- **Primary `artist_id`** for `POST /songs` comes from **fixed wizard context** (`fixedArtistId`) or from a tightly controlled entry point — not from arbitrary cross-artist selection in production.
- **Backend validates** `artist.user_id == current_user.id` before creating the song (403 if mismatch).
- **UI:** no "which artist is this for?" step when context is already correct.
- **Risk if misapplied:** exposing a raw **Artist ID** field to end users is not an acceptable long-term UX; it exists only as a **technical bridge** until a proper **artist selector** (search, roster, permissions) ships with the Label role.

### 3.2 Future behavior (Label role)

When Label (or similar) is implemented, the upload flow **must**:

1. Add an **Artist selector (required)** in Step 1 (or before metadata commit), backed by roster + search — **not** a numeric ID field.
2. **Replace** implicit `fixedArtistId` **for that role** with **explicit selected artist** (still validated server-side).
3. **Validate** on the backend that the authenticated principal may create/update content for that `artist_id` (label-artist relationship + permission checks).

Artist-only flows can keep **hidden** selector (fixed context).

---

## 4. Important current constraint (VERY IMPORTANT)

The `UploadWizard` still contains **conditional** UI roughly of the form:

```tsx
if (!artistLocked) {
  // e.g. Artist ID input — technical, not product-ready
}
```

where `artistLocked` is true when `fixedArtistId` is set.

### Required invariant (until roles ship)

For **all production / product-critical upload entry points**:

- **`artistLocked === true`** (i.e. **`fixedArtistId` is always set** on the wizard for real users).

So:

- The **raw Artist ID** branch must remain **effectively disabled** for customers: every supported upload route should pass **`fixedArtistId`** (or an equivalent "locked context") so users never see internal ID editing.

### Why this matters

If the invariant breaks:

- Users may see a **raw Artist ID** control — poor UX, training burden, and **data integrity** risk (wrong artist, typos, privilege escalation if the API ever trusts client `artist_id` without server-side checks).
- Product appears to support "pick any artist" **without** auth, roster, or label rules — which is **not** true today.

### Action for engineers

- Treat `!artistLocked` UI as **scaffolding for future Label work** or **non-production paths only** — not as a feature to expose broadly.
- Before enabling any public flow without `fixedArtistId`, ship: **roles**, **roster**, **permission checks**, and a **proper artist picker**.

---

## 5. Backend implications (future)

When implementing roles coherently (not piecemeal):

1. **Role model** on users (or orgs): Artist, Label staff, Admin, etc.
2. **Relationships:** Label <-> Artists (one-to-many or many-to-many; include effective dates if needed).
3. **Auth / context:** Resolve **active artist context** (or "acting on behalf of") from token/session + policy, not only from client body.
4. **Enforcement on every write:**
   - **Artist:** only `artist_id` matching self (or explicit admin).
   - **Label:** only `artist_id` in allowed roster.
   - **Admin:** per policy (audited).

`POST /songs` and related endpoints must **never** trust `artist_id` from the client without matching server-side authorization once multiple roles exist.

---

## 6. Frontend implications (future)

Conditional UX by role (conceptual):

| Role            | Artist selector in upload        |
| --------------- | -------------------------------- |
| Artist          | Hidden (fixed to self)           |
| Label           | Required (roster-backed picker)  |
| Admin           | Optional / override (per policy) |
| User / Curator  | N/A (no upload)                  |

Implementation detail: the current `fixedArtistId` prop maps to **"locked context"**; Label mode becomes **"unlocked but constrained picker"**, not an open numeric field.

---

## 7. Design constraints (read before coding)

- **Do not** implement partial role logic without updating **auth**, **permissions**, and **upload pipeline** together.
- **Do not** change current **product** upload behavior in a way that exposes raw artist ID entry to end users without the invariant in section 4 being explicitly lifted by design.
- **Do not** introduce "label upload" UI until backend can **prove** label-artist scope for the selected `artist_id`.

This document is meant to:

- **Prevent accidental regressions** (e.g. shipping a page without `fixedArtistId` and calling it "done").
- **Guide** a single coherent milestone when Label + roles land.

---

## 8. Foundational decision (summary)

Roles + ownership are a **cross-cutting** concern: **DB relationships**, **API authorization**, **upload wizard**, and **admin tools** must move together.

**Do not** ship "Label can pick artist_id in JSON" without "Label can only pick allowed artists" enforced **on the server** and reflected **in the UI** with a proper selector.

When in doubt, preserve **section 4's invariant** until the full slice is ready.

## Related State
- /docs/state/auth.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/auth.md
