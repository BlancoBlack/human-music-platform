# Streaming / listening — current implementation

## CURRENTLY IMPLEMENTED

### Production endpoints (`routes.py`)

- **`POST /stream`**: authenticated listener (`get_listening_user_id`); body includes `song_id`, `duration` (> 0 required), optional `session_id`, `idempotency_key`, `correlation_id`. Delegates to `StreamService.process_stream`.
- **`POST /stream/start-session`**: creates session via `process_start_listening_session` (user + `song_id`); rate-limited per user.
- **`POST /stream/checkpoint`**: `process_stream_checkpoint` with `session_id`, `song_id`, `sequence`, `position_seconds`; separate rate limits from `/stream`.

### Minimum duration and “ignored” events

- **API floor**: `duration < 5` seconds → response `status: "ignored"`, `is_valid: false`, `validation_reason: "short_listen"` — **no** `ListeningEvent` row inserted (`stream_service.py`).
- **Mismatch vs secondary context**: informal “stream definition (duration ≥ 5)” is only this **ingestion gate**. **Economic validity** uses different rules (below).

### Economic validation (`listening_validation.validate_listen`)

Applied **after** the 5s gate, before insert. Computes metadata only; stored on `ListeningEvent`:

- **Duration validity**: requires `real_duration >= threshold` where threshold is `max(30, 0.3 * song_duration_seconds)` when song duration known, else `30` seconds.
- **Repeat spacing**: last **valid** listen same user+song must be **≥ 2 hours** ago (`too_soon_repeat`).
- **Daily cap**: max **5 valid** listens per user+song per **UTC calendar day** (`daily_cap_exceeded`).
- **Weight**: `exp(-0.22 * repeats)` where `repeats` = count of valid listens in last **24h** (including logic that counts prior events before insert).
- **Invalid path**: `is_valid=false`, `validated_duration=0`, `weight=0`, `validation_reason` string tokens.

### `ListeningEvent` model

- Fields include: `user_id` (FK users), `song_id` (integer, **no FK** in model), `session_id` → `listening_sessions`, `duration` (integer seconds), `processed` boolean, `is_valid`, `validated_duration`, `weight`, `validation_reason`, `idempotency_key`, `correlation_id`, timestamps.
- **Partial unique constraint** (Alembic / SQLite patches): `(user_id, idempotency_key)` where `idempotency_key` IS NOT NULL — duplicate requests return `status: "duplicate"` with existing event id.

### Sessions and checkpoints

- **`ListeningSession`**: can be created explicitly by start-session, or implicitly inside `process_stream` if no `session_id` passed (new session created).
- **`ListeningSessionCheckpoint`**: append-only progress; **does not** drive `validate_listen` or payouts (stated in `listening_checkpoint_service` module docstring).
- **SQLite trigger** (startup patch in `main.py`): on insert into `listening_events` with `session_id`, updates `listening_sessions.finalized_at`.

### Session lifecycle constraints (SQLAlchemy)

- `POST /stream/start-session` follows strict ORM order: `add` -> `flush` -> persistence/PK checks -> `refresh` -> `commit`.
- `refresh()` must only run on a **persistent** instance with a generated primary key; calling it on transient/pending rows can raise `InvalidRequestError`.
- `flush()` is used to force INSERT and PK generation without ending the transaction; `commit()` finalizes after successful refresh.
- Session creation now logs before/after flush and logs exceptions with rollback, so first-attempt failures are visible and deterministic.

### Post-commit pipeline

- **RQ**: `queue.enqueue(process_listening_event, event.id)` after successful commit.
- **`listen_worker.process_listening_event`**: idempotent via `processed` flag; updates `ListeningAggregate` (`total_duration`, `weighted_duration` from valid listens only); updates `GlobalListeningAggregate.total_duration` for valid listens (validated duration, **no weight** in global aggregate); sets `event.processed=True`.

### Rate limiting (application layer)

- **`/stream`**: sliding-window limits per IP and per user + burst window (`routes.py` constants; in-memory stores).
- **Checkpoints / start-session**: separate windows and maxima.

### Dev inspection

- **`GET /dev/events`**: query filters (`user_id`, `song_id`, `since_minutes`, `limit`, `only_valid`); requires `require_dev_mode()`.

## PARTIALLY IMPLEMENTED

- **Cross-process / multi-instance rate limits**: in-memory only — not shared across uvicorn workers or hosts.
- **PostgreSQL ingestion serialization**: `_acquire_ingestion_lock` only implements SQLite upsert on `ingestion_locks`; other dialects skip locking and log a warning (see `stream_service.py` TODO).

## NOT IMPLEMENTED

- **Blockchain or payout side effects directly on `POST /stream`**: stream path only enqueues aggregate updates; no settlement or `payout_lines` mutation in this handler.

## KNOWN ISSUES

- **Secondary context claimed “duration ≥ 5” for stream definition**: true for **acceptance** into the pipeline; **valid** streams for economics/analytics require the **30s / 30%** rule and caps above.
- **`ListeningEvent.song_id`**: nullable in DB sense but validated at runtime; ORM lacks FK to `songs` — referential integrity not enforced by SQLite FK for this column.
