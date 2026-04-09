-- PART 1 — Data cleanup (run before schema rebuild; invalid data must NOT be preserved)
DELETE FROM listening_events
WHERE user_id IS NULL
   OR user_id NOT IN (SELECT id FROM users);

-- Verify before continuing (must return 0):
-- SELECT COUNT(*) FROM listening_events
-- WHERE user_id IS NULL OR user_id NOT IN (SELECT id FROM users);

-- PART 4 — SQLite table rebuild: NOT NULL user_id + FK to users(id)
-- PRAGMA foreign_keys must be toggled outside an active transaction.

PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

CREATE TABLE listening_events_new (
    id INTEGER NOT NULL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    song_id INTEGER,
    session_id INTEGER,
    weight REAL,
    timestamp DATETIME,
    created_at DATETIME,
    duration INTEGER,
    processed INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (session_id) REFERENCES listening_sessions (id)
);

INSERT INTO listening_events_new (
    id,
    user_id,
    song_id,
    session_id,
    weight,
    timestamp,
    created_at,
    duration,
    processed
)
SELECT
    id,
    user_id,
    song_id,
    session_id,
    weight,
    timestamp,
    created_at,
    duration,
    processed
FROM listening_events;

DROP TABLE listening_events;

ALTER TABLE listening_events_new RENAME TO listening_events;

CREATE INDEX ix_listening_events_created_at
ON listening_events (created_at);

CREATE INDEX ix_listening_events_song_id_created_at
ON listening_events (song_id, created_at);

CREATE INDEX ix_listening_events_user_id_created_at
ON listening_events (user_id, created_at);

CREATE INDEX ix_listening_events_user_id_song_id_created_at
ON listening_events (user_id, song_id, created_at);

COMMIT;

PRAGMA foreign_keys = ON;
