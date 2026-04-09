-- Add payout execution safety fields on payouts (SQLite).
-- Apply from backend/: sqlite3 test.db < migrations/005_payout_execution_safety_fields.sql

ALTER TABLE payouts ADD COLUMN idempotency_key VARCHAR(128);
ALTER TABLE payouts ADD COLUMN destination_wallet VARCHAR(255);
ALTER TABLE payouts ADD COLUMN algorand_tx_id VARCHAR(128);
ALTER TABLE payouts ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE payouts ADD COLUMN failure_reason TEXT;
ALTER TABLE payouts ADD COLUMN processing_started_at DATETIME;
ALTER TABLE payouts ADD COLUMN processed_at DATETIME;

CREATE INDEX IF NOT EXISTS ix_payouts_status ON payouts (status);
CREATE INDEX IF NOT EXISTS ix_payouts_idempotency_key ON payouts (idempotency_key);
