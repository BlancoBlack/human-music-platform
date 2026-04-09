-- Create payout ledger v2 tables (SQLite).
-- Apply from backend/: sqlite3 test.db < migrations/007_payout_ledger_v2_tables.sql

CREATE TABLE IF NOT EXISTS payout_batches (
    id INTEGER PRIMARY KEY,
    period_start_at DATETIME NOT NULL,
    period_end_at DATETIME NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    calculation_version VARCHAR(64) NOT NULL DEFAULT 'v2',
    antifraud_version VARCHAR(64) NOT NULL DEFAULT 'v1',
    source_snapshot_hash VARCHAR(128) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finalized_at DATETIME,
    CONSTRAINT ck_payout_batches_period_order CHECK (period_end_at > period_start_at),
    CONSTRAINT ck_payout_batches_status CHECK (status IN ('draft', 'calculating', 'finalized', 'posted')),
    CONSTRAINT ck_payout_batches_currency_len CHECK (length(currency) = 3)
);

CREATE INDEX IF NOT EXISTS ix_payout_batches_status ON payout_batches (status);

CREATE TABLE IF NOT EXISTS payout_lines (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    song_id INTEGER NOT NULL,
    artist_id INTEGER NOT NULL,
    amount_cents BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    line_type VARCHAR(32) NOT NULL DEFAULT 'royalty',
    idempotency_key VARCHAR(128) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_payout_lines_amount_non_negative CHECK (amount_cents >= 0),
    CONSTRAINT ck_payout_lines_line_type CHECK (line_type IN ('royalty', 'treasury', 'adjustment')),
    CONSTRAINT ck_payout_lines_currency_len CHECK (length(currency) = 3),
    CONSTRAINT uq_payout_lines_batch_idempotency UNIQUE (batch_id, idempotency_key),
    FOREIGN KEY(batch_id) REFERENCES payout_batches(id),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(song_id) REFERENCES songs(id),
    FOREIGN KEY(artist_id) REFERENCES artists(id)
);

CREATE INDEX IF NOT EXISTS ix_payout_lines_batch_id ON payout_lines (batch_id);
CREATE INDEX IF NOT EXISTS ix_payout_lines_user_id ON payout_lines (user_id);
CREATE INDEX IF NOT EXISTS ix_payout_lines_song_id ON payout_lines (song_id);
CREATE INDEX IF NOT EXISTS ix_payout_lines_artist_id ON payout_lines (artist_id);
