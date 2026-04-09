-- ListeningEvent reliability hardening:
-- - add processed flag for worker idempotency
-- - add analytics indexes on created_at dimensions

BEGIN TRANSACTION;

ALTER TABLE listening_events
ADD COLUMN processed INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS ix_listening_events_created_at
ON listening_events (created_at);

CREATE INDEX IF NOT EXISTS ix_listening_events_song_id_created_at
ON listening_events (song_id, created_at);

CREATE INDEX IF NOT EXISTS ix_listening_events_user_id_created_at
ON listening_events (user_id, created_at);

CREATE INDEX IF NOT EXISTS ix_listening_events_user_id_song_id_created_at
ON listening_events (user_id, song_id, created_at);

COMMIT;
