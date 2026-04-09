-- Payout ledger v2 hardening (SQLite).
-- Apply from backend/: sqlite3 test.db < migrations/008_payout_ledger_v2_hardening.sql

-- 1) Make payout_batches.source_snapshot_hash nullable
-- SQLite cannot alter column nullability in-place, so we rebuild only this table.
BEGIN TRANSACTION;
PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS payout_batches_old;
DROP INDEX IF EXISTS ix_payout_batches_status_v2;

ALTER TABLE payout_batches RENAME TO payout_batches_old;

CREATE TABLE payout_batches (
    id INTEGER PRIMARY KEY,
    period_start_at DATETIME NOT NULL,
    period_end_at DATETIME NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    calculation_version VARCHAR(64) NOT NULL DEFAULT 'v2',
    antifraud_version VARCHAR(64) NOT NULL DEFAULT 'v1',
    source_snapshot_hash VARCHAR(128) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finalized_at DATETIME,
    CONSTRAINT ck_payout_batches_period_order CHECK (period_end_at > period_start_at),
    CONSTRAINT ck_payout_batches_status CHECK (status IN ('draft', 'calculating', 'finalized', 'posted')),
    CONSTRAINT ck_payout_batches_currency_len CHECK (length(currency) = 3)
);

-- Recreate status index using the original name.
DROP INDEX IF EXISTS ix_payout_batches_status;
CREATE INDEX ix_payout_batches_status ON payout_batches (status);

-- Copy existing rows forward.
INSERT INTO payout_batches (
    id,
    period_start_at,
    period_end_at,
    status,
    currency,
    calculation_version,
    antifraud_version,
    source_snapshot_hash,
    created_at,
    finalized_at
)
SELECT
    id,
    period_start_at,
    period_end_at,
    status,
    currency,
    calculation_version,
    antifraud_version,
    source_snapshot_hash,
    created_at,
    finalized_at
FROM payout_batches_old;

COMMIT;

-- 2) Increase payout_lines.idempotency_key VARCHAR length (schema refresh).
-- SQLite does not enforce VARCHAR length, but this keeps the schema aligned for future DBs.
BEGIN TRANSACTION;
PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS payout_lines_old;
DROP INDEX IF EXISTS ix_payout_lines_v2_batch_id;
DROP INDEX IF EXISTS ix_payout_lines_v2_user_id;
DROP INDEX IF EXISTS ix_payout_lines_v2_song_id;
DROP INDEX IF EXISTS ix_payout_lines_v2_artist_id;
DROP INDEX IF EXISTS uq_payout_lines_batch_idempotency_v2;
DROP INDEX IF EXISTS uq_payout_lines_batch_idempotency;

ALTER TABLE payout_lines RENAME TO payout_lines_old;

CREATE TABLE payout_lines (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    song_id INTEGER NOT NULL,
    artist_id INTEGER NOT NULL,
    amount_cents BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    line_type VARCHAR(32) NOT NULL DEFAULT 'royalty',
    idempotency_key VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_payout_lines_amount_non_negative CHECK (amount_cents >= 0),
    CONSTRAINT ck_payout_lines_line_type CHECK (line_type IN ('royalty', 'treasury', 'adjustment')),
    CONSTRAINT ck_payout_lines_currency_len CHECK (length(currency) = 3),
    FOREIGN KEY(batch_id) REFERENCES payout_batches(id),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(song_id) REFERENCES songs(id),
    FOREIGN KEY(artist_id) REFERENCES artists(id)
);

-- Recreate indexes (use new names to avoid collisions with indexes attached to the _old table).
CREATE INDEX ix_payout_lines_v2_batch_id ON payout_lines (batch_id);
CREATE INDEX ix_payout_lines_v2_user_id ON payout_lines (user_id);
CREATE INDEX ix_payout_lines_v2_song_id ON payout_lines (song_id);
CREATE INDEX ix_payout_lines_v2_artist_id ON payout_lines (artist_id);

-- Recreate unique idempotency constraint via a unique index.
CREATE UNIQUE INDEX uq_payout_lines_batch_idempotency_v2 ON payout_lines (batch_id, idempotency_key);

-- Copy existing rows forward.
INSERT INTO payout_lines (
    id,
    batch_id,
    user_id,
    song_id,
    artist_id,
    amount_cents,
    currency,
    line_type,
    idempotency_key,
    created_at
)
SELECT
    id,
    batch_id,
    user_id,
    song_id,
    artist_id,
    amount_cents,
    currency,
    line_type,
    idempotency_key,
    created_at
FROM payout_lines_old;

COMMIT;

-- 3) Add composite performance indexes
CREATE INDEX IF NOT EXISTS ix_payout_lines_batch_artist_id ON payout_lines (batch_id, artist_id);
CREATE INDEX IF NOT EXISTS ix_payout_lines_batch_user_id ON payout_lines (batch_id, user_id);

-- Cleanup legacy artifacts created during migration rebuilds.
DROP TABLE IF EXISTS payout_batches_old;
DROP TABLE IF EXISTS payout_lines_old;

