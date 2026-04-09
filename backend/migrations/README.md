# Database migrations

## `001_song_artist_splits_constraints.sql`

Adds SQLite constraints on `song_artist_splits` to match `app.models.song_artist_split.SongArtistSplit`:

| Constraint | Purpose |
|------------|---------|
| `song_id NOT NULL` | Every split row belongs to a song. |
| `artist_id NOT NULL` | Every split row assigns to an artist. |
| `share NOT NULL` | Share is always explicit. |
| `CHECK (share > 0 AND share <= 1)` | Each row’s share is a valid fraction. |
| `UNIQUE (song_id, artist_id)` | At most one row per artist per song. |

**Apply** (from `backend/`, with your DB path):

```bash
sqlite3 test.db < migrations/001_song_artist_splits_constraints.sql
```

**Fresh installs:** `Base.metadata.create_all()` in `app/main.py` will create the table with these constraints from the SQLAlchemy model.

### SUM(share) = 1 per song (not in DB)

SQLite triggers run **per row** (`AFTER INSERT` / `UPDATE` / `DELETE`). After inserting the first row of a multi-artist song, **SUM(share) < 1** until the rest of the rows exist, so a **row-level trigger would reject valid partial inserts** unless all rows are inserted in one statement or intermediate states are allowed.

**Reliable approach:** keep enforcing **Σ share = 1 per song** in the API (`validate_song_splits`) and in **runtime** (`split_song_amount_to_artists` fail-fast). A **deferred** `SUM = 1` check would require SQLite features that don’t apply cleanly to multi-row INSERTs; optional mitigation is a **scheduled integrity query** or a **transaction-scoped** validation in application code.

## `003_listening_event_user_fk.sql`

1. Deletes `listening_events` with `user_id IS NULL` or orphan `user_id`.
2. Rebuilds `listening_events` with `user_id NOT NULL` and `FOREIGN KEY (user_id) REFERENCES users (id)` (and `session_id` → `listening_sessions`).
3. Recreates analytics indexes from `002_listening_event_integrity.sql`.

**Before applying:** run the verification `SELECT` in the script comments; count must be `0` after the `DELETE`.

**Apply** (from `backend/`):

```bash
sqlite3 test.db < migrations/003_listening_event_user_fk.sql
sqlite3 test.db "PRAGMA foreign_key_check;"
```

Ensure app connections use `PRAGMA foreign_keys=ON` (see `app/core/database.py`).

## `004_artist_payout_method.sql`

Adds artist payout preference columns (`payout_method`, `payout_wallet_address`, `payout_bank_info`) for MVP configuration (no execution).

**Apply** (from `backend/`):

```bash
sqlite3 test.db < migrations/004_artist_payout_method.sql
```

**Fresh installs:** new columns are created via `Base.metadata.create_all()` from `app.models.artist.Artist` — **do not** run this script if the table was already created with those columns (SQLite would error on duplicate column).


## `005_payout_execution_safety_fields.sql`

Adds backward-compatible payout execution fields on `payouts`:
`idempotency_key`, `destination_wallet`, `algorand_tx_id`, `attempt_count`, `failure_reason`, `processing_started_at`, `processed_at`.

Also creates indexes for `status` and `idempotency_key`.

**Apply** (from `backend/`):

```bash
sqlite3 test.db < migrations/005_payout_execution_safety_fields.sql
```
