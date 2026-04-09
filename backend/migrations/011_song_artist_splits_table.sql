-- Ensure song_artist_splits table exists with split_bps constraints (SQLite).
-- Safe no-op if table already exists.
-- Apply from backend/: sqlite3 test.db < migrations/011_song_artist_splits_table.sql

CREATE TABLE IF NOT EXISTS song_artist_splits (
    id INTEGER PRIMARY KEY,
    song_id INTEGER NOT NULL,
    artist_id INTEGER NOT NULL,
    split_bps INTEGER NOT NULL,
    CHECK (split_bps >= 0 AND split_bps <= 10000),
    FOREIGN KEY(song_id) REFERENCES songs(id),
    FOREIGN KEY(artist_id) REFERENCES artists(id),
    CONSTRAINT uq_song_artist_splits_song_artist UNIQUE (song_id, artist_id)
);

