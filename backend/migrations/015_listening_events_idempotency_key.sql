-- Idempotent stream submits: one row per (user_id, idempotency_key) when key is set.
-- SQLite: multiple NULL idempotency_key values are allowed under UNIQUE.

ALTER TABLE listening_events ADD COLUMN idempotency_key VARCHAR(128);

CREATE UNIQUE INDEX IF NOT EXISTS uq_listening_events_user_idempotency
ON listening_events (user_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;
