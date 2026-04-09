-- Settlement hardening: wallet snapshot + splits digest for audit.

ALTER TABLE payout_settlements ADD COLUMN destination_wallet VARCHAR(255);
ALTER TABLE payout_settlements ADD COLUMN splits_digest VARCHAR(64);
