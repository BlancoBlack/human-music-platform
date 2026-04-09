-- Create payout engine snapshot tables (v2 MVP).
-- Apply from backend/: sqlite3 test.db < migrations/009_payout_snapshot_tables.sql

CREATE TABLE IF NOT EXISTS payout_input_snapshots (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL,
    period_start_at DATETIME NOT NULL,
    period_end_at DATETIME NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    calculation_version VARCHAR(64) NOT NULL DEFAULT 'v2',
    antifraud_version VARCHAR(64) NOT NULL DEFAULT 'v1',
    listening_aggregation_version VARCHAR(64) NOT NULL DEFAULT 'v1',
    policy_id VARCHAR(64) NOT NULL DEFAULT 'v1',
    policy_artist_share REAL NOT NULL DEFAULT 0.70,
    policy_weight_decay_lambda REAL NOT NULL DEFAULT 0.22,
    policy_json TEXT,
    source_time_cutoff DATETIME NOT NULL,
    snapshot_state VARCHAR(16) NOT NULL DEFAULT 'draft',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sealed_at DATETIME,
    snapshot_user_pool_sum_cents BIGINT,
    snapshot_listening_raw_units_sum BIGINT,
    snapshot_listening_qualified_units_sum BIGINT,
    CONSTRAINT ck_payout_input_snapshots_period_order CHECK (period_end_at > period_start_at),
    CONSTRAINT ck_payout_input_snapshots_state CHECK (snapshot_state IN ('draft', 'sealed')),
    CONSTRAINT ck_payout_input_snapshots_currency_len CHECK (length(currency) = 3),
    CONSTRAINT ck_payout_input_snapshots_user_pool_sum_non_negative CHECK (snapshot_user_pool_sum_cents IS NULL OR snapshot_user_pool_sum_cents >= 0),
    CONSTRAINT ck_payout_input_snapshots_raw_units_sum_non_negative CHECK (snapshot_listening_raw_units_sum IS NULL OR snapshot_listening_raw_units_sum >= 0),
    CONSTRAINT ck_payout_input_snapshots_qualified_units_sum_non_negative CHECK (snapshot_listening_qualified_units_sum IS NULL OR snapshot_listening_qualified_units_sum >= 0),
    CONSTRAINT ck_payout_input_snapshots_policy_artist_share_range CHECK (policy_artist_share >= 0 AND policy_artist_share <= 1),
    CONSTRAINT ck_payout_input_snapshots_policy_weight_decay_non_negative CHECK (policy_weight_decay_lambda >= 0),
    FOREIGN KEY(batch_id) REFERENCES payout_batches(id)
);

CREATE INDEX IF NOT EXISTS ix_payout_input_snapshots_batch_id ON payout_input_snapshots (batch_id);
CREATE INDEX IF NOT EXISTS ix_payout_input_snapshots_state ON payout_input_snapshots (snapshot_state);
CREATE INDEX IF NOT EXISTS ix_payout_input_snapshots_policy_id ON payout_input_snapshots (policy_id);

CREATE TABLE IF NOT EXISTS snapshot_user_pools (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    user_pool_cents BIGINT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_snapshot_user_pools_snapshot_user UNIQUE (snapshot_id, user_id),
    CONSTRAINT ck_snapshot_user_pools_user_pool_cents_non_negative CHECK (user_pool_cents >= 0),
    FOREIGN KEY(snapshot_id) REFERENCES payout_input_snapshots(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_snapshot_user_pools_snapshot_id ON snapshot_user_pools (snapshot_id);
CREATE INDEX IF NOT EXISTS ix_snapshot_user_pools_user_id ON snapshot_user_pools (user_id);

CREATE TABLE IF NOT EXISTS snapshot_listening_inputs (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    song_id INTEGER NOT NULL,
    raw_units_i BIGINT NOT NULL,
    qualified_units_i BIGINT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_snapshot_listening_inputs_snapshot_user_song UNIQUE (snapshot_id, user_id, song_id),
    CONSTRAINT ck_snapshot_listening_inputs_raw_units_non_negative CHECK (raw_units_i >= 0),
    CONSTRAINT ck_snapshot_listening_inputs_qualified_units_non_negative CHECK (qualified_units_i >= 0),
    FOREIGN KEY(snapshot_id) REFERENCES payout_input_snapshots(id),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(song_id) REFERENCES songs(id)
);

CREATE INDEX IF NOT EXISTS ix_snapshot_listening_inputs_snapshot_id ON snapshot_listening_inputs (snapshot_id);
CREATE INDEX IF NOT EXISTS ix_snapshot_listening_inputs_user_song ON snapshot_listening_inputs (user_id, song_id);

