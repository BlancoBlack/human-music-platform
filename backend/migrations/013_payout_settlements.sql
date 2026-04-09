-- V2 on-chain settlement: one row per (batch_id, artist_id).

CREATE TABLE IF NOT EXISTS payout_settlements (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    artist_id INTEGER NOT NULL,
    total_cents INTEGER NOT NULL,
    breakdown_json TEXT NOT NULL,
    breakdown_hash VARCHAR(64) NOT NULL,
    algorand_tx_id VARCHAR(128),
    execution_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    failure_reason TEXT,
    submitted_at DATETIME,
    confirmed_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT fk_payout_settlements_batch
        FOREIGN KEY (batch_id) REFERENCES payout_batches (id),
    CONSTRAINT fk_payout_settlements_artist
        FOREIGN KEY (artist_id) REFERENCES artists (id),
    CONSTRAINT ck_payout_settlements_total_non_negative
        CHECK (total_cents >= 0),
    CONSTRAINT ck_payout_settlements_attempt_non_negative
        CHECK (attempt_count >= 0),
    CONSTRAINT ck_payout_settlements_execution_status
        CHECK (execution_status IN ('pending', 'submitted', 'confirmed', 'failed')),
    CONSTRAINT uq_payout_settlements_batch_artist UNIQUE (batch_id, artist_id)
);

CREATE INDEX IF NOT EXISTS ix_payout_settlements_batch_id ON payout_settlements (batch_id);
CREATE INDEX IF NOT EXISTS ix_payout_settlements_artist_id ON payout_settlements (artist_id);
CREATE INDEX IF NOT EXISTS ix_payout_settlements_breakdown_hash ON payout_settlements (breakdown_hash);
CREATE INDEX IF NOT EXISTS ix_payout_settlements_execution_status ON payout_settlements (execution_status);
