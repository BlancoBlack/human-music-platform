# Tech debt: Media storage architecture (UUID, CDN, signed URLs)

Object storage, delivery, and identity for master audio and cover art. Local filesystem + readable filenames are correct for MVP debugging; they are not the long-term platform shape.

---

## Media storage architecture (UUID, CDN, signed URLs)

**Description**  
Uploaded audio (and, to a lesser extent, covers) are stored **on the local filesystem** under `/uploads`, with **human-readable filenames** such as `song_{id}__{artist-slug}__{title-slug}__master.wav`. Metadata slugs aid debugging and directory browsing during MVP. There is **no abstraction** between **storage backend**, **delivery URL**, and **logical identity** (song / `SongMediaAsset`): the API exposes paths like `/uploads/...` that map directly to disk layout.

**Why it matters**  
- **Scalability:** A single server disk does not scale to thousands of songs, multi-region traffic, or bursty upload/read patterns; long, slug-derived names add edge cases (length limits, normalization, collisions on case-insensitive FS).  
- **Security:** Public static URLs under `/uploads` cannot express **private or unreleased** tracks; there is no **signed URL** or time-limited access model.  
- **Performance:** No **CDN** in front of bytes; API host serves large files.  
- **Decoupling:** Clients and APIs should eventually depend on **stable object keys** (e.g. UUID) and **policy-driven URLs**, not on filename conventions or mount paths.

**Current behavior**  
- FastAPI mounts **`/uploads`** to the local `uploads/` directory.  
- Master WAV filenames embed **song id + derived artist/title** segments for operator visibility.  
- **`GET /songs/{id}`**, catalog responses, and similar surfaces return **`audio_url` / `cover_url`** as **relative paths** (or path-shaped strings) pointing at that static tree.  
- **Identity** in the database (`Song`, `SongMediaAsset.file_path`) is tied to those paths.

**Proposed solution**  
- **Storage keys:** Persist **opaque keys** (e.g. UUID per object) in DB; **do not** encode title/artist in the key used for identity or routing. Keep human labels **only in DB columns**.  
- **Abstraction layer:** Introduce a small **storage interface** (put/get/delete, optional head) with a **local adapter** (MVP) and **S3/GCS (or compatible)** adapter for production.  
- **Delivery:** Front large reads with a **CDN** (origin = object bucket or signed origin); API returns **URLs produced by the abstraction** (absolute HTTPS), not raw filesystem paths.  
- **API evolution:** Prefer a **`stream_url`** (or nested `playback.url`) that may be **signed and short-lived**, alongside or instead of a permanent **`audio_url`** where policy requires it. Document deprecation of path-shaped fields when signing lands.  
- **Private / unreleased:** Gate generation of playback URLs on **`playable`** (or stronger policy) and issue **signed URLs** only when allowed.  
- **Migration:** Backfill object keys; copy or re-upload blobs; cut over readers; retire path assumptions in clients.

**Priority:** MEDIUM  

**When to address:** **Before public release** or **when moving to production infra** where scale, egress, or unreleased-track policy matters—whichever comes first. Not blocking MVP iteration on a single-node dev/staging setup.

---

## Transcoding: WAV masters → MP3 / FLAC (or other derivatives)

**Description**  
Upload pipeline accepts **master WAV** (validated size/type) and stores that object; there is **no automated transcoding** to MP3, FLAC, AAC, or other delivery formats (including downsampled 16-bit or loudness-normalized variants).

**Why it matters**  
Bandwidth, mobile playback, and partner integrations often expect compressed or alternate lossless derivatives; keeping a single huge WAV per song increases egress cost and client buffer pressure.

**Current behavior**  
Single master WAV on disk / served path; client plays WAV URL (see also [player.md](./player.md) buffering discussion).

**Proposed solution**  
- Background job after upload: ffmpeg (or managed transcoder) → e.g. MP3 + FLAC keys in object storage.  
- `Song` / `SongMediaAsset`: multiple renditions with `kind` + bitrate; API returns preferred URL per client.  
- Coordinate with the **object-key + signed URL** direction documented earlier in this file.

**Priority:** MEDIUM  

**When to address:** Before broad mobile / metered-network launch or when CDN egress cost matters; optional for dev-only iteration.

---

*File added to capture storage/delivery debt explicitly; complements API and ingestion docs.*
