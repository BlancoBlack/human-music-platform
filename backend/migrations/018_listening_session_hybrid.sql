-- Hybrid listening: session song binding, finalized_at, checkpoints table.
-- Checkpoints do not participate in payouts; ListeningEvent remains source of truth.
--
-- Apply from backend/:
--   sqlite3 test.db < migrations/018_listening_session_hybrid.sql
--   sqlite3 test.db "PRAGMA foreign_key_check;"

BEGIN TRANSACTION;

-- listening_sessions: bind to one song; mark finalized without changing app code
-- (trigger below sets finalized_at when a listening_event row is inserted).

ALTER TABLE listening_sessions ADD COLUMN song_id INTEGER REFERENCES songs (id);

ALTER TABLE listening_sessions ADD COLUMN finalized_at DATETIME;

-- Historical rows: any session that already has a listening event is finalized.
UPDATE listening_sessions
SET finalized_at = (
  SELECT MIN(le.created_at)
  FROM listening_events le
  WHERE le.session_id = listening_sessions.id
)
WHERE finalized_at IS NULL
  AND EXISTS (
    SELECT 1
    FROM listening_events le
    WHERE le.session_id = listening_sessions.id
  );

CREATE TABLE listening_session_checkpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES listening_sessions (id),
  user_id INTEGER NOT NULL REFERENCES users (id),
  song_id INTEGER NOT NULL REFERENCES songs (id),
  sequence INTEGER NOT NULL,
  position_seconds INTEGER NOT NULL,
  created_at DATETIME NOT NULL DEFAULT (datetime ('now')),
  UNIQUE (session_id, sequence)
);

CREATE INDEX ix_listening_session_checkpoints_session_id
  ON listening_session_checkpoints (session_id);

CREATE INDEX ix_listening_session_checkpoints_user_id_created_at
  ON listening_session_checkpoints (user_id, created_at);

-- When a listening event is attached to a session, freeze the session for checkpoints.
CREATE TRIGGER tr_listening_events_mark_session_finalized
AFTER INSERT ON listening_events
FOR EACH ROW
WHEN NEW.session_id IS NOT NULL
BEGIN
  UPDATE listening_sessions
  SET finalized_at = COALESCE(finalized_at, NEW.created_at)
  WHERE id = NEW.session_id;
END;

COMMIT;
