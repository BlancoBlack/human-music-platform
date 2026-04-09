-- Bind payout_batches -> payout_input_snapshots (nullable FK, SQLite).
-- Apply from backend/: sqlite3 test.db < migrations/012_payout_batches_snapshot_id.sql

ALTER TABLE payout_batches ADD COLUMN snapshot_id INTEGER REFERENCES payout_input_snapshots(id);
CREATE INDEX IF NOT EXISTS ix_payout_batches_snapshot_id ON payout_batches (snapshot_id);

