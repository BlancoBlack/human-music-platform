-- Add split_bps to song_artist_splits with strict constraints (SQLite).
-- Apply from backend/: sqlite3 test.db < migrations/010_song_artist_splits_split_bps.sql
--
-- Notes:
-- - SQLite cannot add CHECK constraints to an existing column via ALTER TABLE.
--   We rebuild the table.
-- - We backfill split_bps from existing share as ROUND(share * 10000).
--   Runtime resolver MUST still validate sum(split_bps) == 10000.

PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

CREATE TABLE song_artist_splits__new (
    id INTEGER NOT NULL PRIMARY KEY,
    song_id INTEGER NOT NULL,
    artist_id INTEGER NOT NULL,
    share REAL NOT NULL,
    split_bps INTEGER NOT NULL,
    CHECK (share > 0 AND share <= 1),
    CHECK (split_bps >= 0 AND split_bps <= 10000),
    FOREIGN KEY (song_id) REFERENCES songs (id),
    FOREIGN KEY (artist_id) REFERENCES artists (id),
    CONSTRAINT uq_song_artist_splits_song_artist UNIQUE (song_id, artist_id)
);

INSERT INTO song_artist_splits__new (id, song_id, artist_id, share, split_bps)
SELECT
    id,
    song_id,
    artist_id,
    share,
    CAST(ROUND(share * 10000) AS INTEGER) AS split_bps
FROM song_artist_splits;

DROP TABLE song_artist_splits;
ALTER TABLE song_artist_splits__new RENAME TO song_artist_splits;

CREATE INDEX IF NOT EXISTS ix_song_artist_splits_id ON song_artist_splits (id);
CREATE INDEX IF NOT EXISTS ix_song_artist_splits_song_id ON song_artist_splits (song_id);
CREATE INDEX IF NOT EXISTS ix_song_artist_splits_artist_id ON song_artist_splits (artist_id);

COMMIT;
PRAGMA foreign_keys = ON;

