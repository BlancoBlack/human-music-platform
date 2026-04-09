-- ListeningEvent validation enrichment (Phase 1): add columns for economic
-- validation metadata without changing payout/aggregation math.

BEGIN TRANSACTION;

ALTER TABLE listening_events
ADD COLUMN is_valid BOOLEAN NOT NULL DEFAULT 0;

ALTER TABLE listening_events
ADD COLUMN validated_duration REAL NOT NULL DEFAULT 0;

ALTER TABLE listening_events
ADD COLUMN validation_reason TEXT;

COMMIT;

