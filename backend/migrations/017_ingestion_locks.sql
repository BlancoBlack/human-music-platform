-- Serialize validate_listen + ListeningEvent insert per (user_id, song_id) under SQLite.

CREATE TABLE IF NOT EXISTS ingestion_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    song_id INTEGER NOT NULL,
    locked_at DATETIME NOT NULL,
    UNIQUE (user_id, song_id)
);
