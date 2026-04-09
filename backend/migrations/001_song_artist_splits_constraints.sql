-- SQLite: enforce NOT NULL, CHECK, UNIQUE on song_artist_splits.
-- Apply once to existing DBs created before these constraints.
-- Current data must already satisfy: no NULLs, shares in (0,1], no duplicate (song_id, artist_id).

PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

CREATE TABLE song_artist_splits__new (
    id INTEGER NOT NULL PRIMARY KEY,
    song_id INTEGER NOT NULL,
    artist_id INTEGER NOT NULL,
    share REAL NOT NULL,
    CHECK (share > 0 AND share <= 1),
    FOREIGN KEY (song_id) REFERENCES songs (id),
    FOREIGN KEY (artist_id) REFERENCES artists (id),
    CONSTRAINT uq_song_artist_splits_song_artist UNIQUE (song_id, artist_id)
);

INSERT INTO song_artist_splits__new (id, song_id, artist_id, share)
SELECT id, song_id, artist_id, share
FROM song_artist_splits;

DROP TABLE song_artist_splits;
ALTER TABLE song_artist_splits__new RENAME TO song_artist_splits;

CREATE INDEX IF NOT EXISTS ix_song_artist_splits_id ON song_artist_splits (id);

COMMIT;
PRAGMA foreign_keys = ON;
