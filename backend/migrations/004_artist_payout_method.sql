-- Add payout method fields on artists (SQLite).
-- Apply from backend/: sqlite3 test.db < migrations/004_artist_payout_method.sql

ALTER TABLE artists ADD COLUMN payout_method VARCHAR(32) NOT NULL DEFAULT 'none';
ALTER TABLE artists ADD COLUMN payout_wallet_address VARCHAR(255);
ALTER TABLE artists ADD COLUMN payout_bank_info VARCHAR(255);
