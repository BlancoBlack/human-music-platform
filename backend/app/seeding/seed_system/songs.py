from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.genre import Genre
from app.models.release import Release
from app.models.song import Song
from app.models.subgenre import Subgenre


def resolve_seed_genre_ids(db: Session) -> tuple[int, int]:
    genre = db.query(Genre).filter(Genre.slug == "electronic").one()
    subgenre = (
        db.query(Subgenre)
        .filter(Subgenre.genre_id == int(genre.id), Subgenre.slug == "house")
        .one_or_none()
    )
    if subgenre is None:
        subgenre = db.query(Subgenre).filter(Subgenre.genre_id == int(genre.id)).order_by(Subgenre.id.asc()).first()
    if subgenre is None:
        raise RuntimeError("No subgenre rows available for electronic genre seed.")
    return int(genre.id), int(subgenre.id)


def _catalog_for_artist(artist_name: str, artist_idx: int) -> list[dict[str, object]]:
    duplicate_single_title = "Midnight Pulse" if artist_idx in (1, 2) else f"{artist_name} Signal"
    return [
        {"release_key": "album", "title": f"{artist_name} Dawn I", "moods": ["uplifting", "focus"], "duration": 215},
        {"release_key": "album", "title": f"{artist_name} Dawn II", "moods": ["dreamy", "late night"], "duration": 234},
        {"release_key": "album", "title": f"{artist_name} Dawn III", "moods": ["chill", "ambient"], "duration": 208},
        {"release_key": "ep", "title": f"{artist_name} Tides", "moods": ["melancholic", "cinematic"], "duration": 195},
        {"release_key": "ep", "title": f"{artist_name} Tides Reprise", "moods": ["energetic", "workout"], "duration": 187},
        {"release_key": "single", "title": duplicate_single_title, "moods": ["energetic", "focus"], "duration": 201},
    ]


def upsert_artist_songs(
    db: Session,
    *,
    artist: Artist,
    artist_idx: int,
    releases: dict[str, Release],
    genre_id: int,
    subgenre_id: int,
    song_state: str,
    file_path: str,
) -> list[Song]:
    songs: list[Song] = []
    for track_idx, spec in enumerate(_catalog_for_artist(str(artist.name), artist_idx), start=1):
        release = releases[str(spec["release_key"])]
        system_key = f"seed.song.artist{artist_idx:02d}.track{track_idx:02d}"
        row = db.query(Song).filter(Song.system_key == system_key).one_or_none()
        if row is None:
            row = Song(
                title=str(spec["title"]),
                system_key=system_key,
                artist_id=int(artist.id),
                release_id=int(release.id),
                track_number=track_idx,
                genre_id=genre_id,
                subgenre_id=subgenre_id,
                moods=list(spec["moods"]),  # type: ignore[arg-type]
                duration_seconds=int(spec["duration"]),
                file_path=file_path,
                upload_status="ready",
                state=song_state,
                is_system=False,
            )
            db.add(row)
        else:
            row.title = str(spec["title"])
            row.artist_id = int(artist.id)
            target_release_id = int(release.id)
            current_release_id = int(row.release_id or 0)
            if current_release_id != target_release_id:
                current_state = getattr(row.state, "value", row.state)
                if str(current_state or "") == "ready_for_release":
                    raise RuntimeError(
                        f"Seed lifecycle violation: song {int(row.id)} is ready_for_release "
                        "and cannot change release membership."
                    )
                row.release_id = target_release_id
            row.track_number = track_idx
            row.genre_id = genre_id
            row.subgenre_id = subgenre_id
            row.moods = list(spec["moods"])  # type: ignore[arg-type]
            row.duration_seconds = int(spec["duration"])
            row.file_path = file_path
            row.upload_status = "ready"
            row.state = song_state
            row.is_system = False
            row.deleted_at = None
        db.flush()
        songs.append(row)
    return songs
