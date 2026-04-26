from app.core.database import SessionLocal
from app.economics_constants import ARTIST_SHARE
from app.models.artist import Artist
from app.models.listening_aggregate import ListeningAggregate
from app.models.song import Song
from app.services.slug_service import ensure_artist_slug, ensure_song_slug, update_artist_slug, update_song_slug
from app.models.user_balance import UserBalance
from sqlalchemy.exc import IntegrityError
import math

EPSILON = 1e-12
TREASURY_ARTIST_NAME = "TREASURY"
TREASURY_SONG_TITLE = "TREASURY_SINK"
TREASURY_ARTIST_SYSTEM_KEY = "TREASURY"
TREASURY_SONG_SYSTEM_KEY = "TREASURY_SINK"


def get_treasury_artist(db):
    matches = db.query(Artist).filter_by(system_key=TREASURY_ARTIST_SYSTEM_KEY).all()
    if len(matches) > 1:
        raise RuntimeError("Multiple treasury artists found — system invariant broken")
    return matches[0] if matches else None


def is_system_song(song) -> bool:
    return bool(song is not None and getattr(song, "is_system", False))


def is_system_artist(artist) -> bool:
    return bool(artist is not None and getattr(artist, "is_system", False))


def ensure_treasury_entities(db) -> tuple[Artist, Song]:
    treasury_artist = get_treasury_artist(db)
    if treasury_artist is None:
        legacy = db.query(Artist).filter_by(name=TREASURY_ARTIST_NAME).one_or_none()
        if legacy is not None:
            legacy.system_key = TREASURY_ARTIST_SYSTEM_KEY
            legacy.is_system = True
            treasury_artist = legacy
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                treasury_artist = get_treasury_artist(db)
        else:
            treasury_artist = Artist(
                name=TREASURY_ARTIST_NAME,
                system_key=TREASURY_ARTIST_SYSTEM_KEY,
                is_system=True,
            )
            db.add(treasury_artist)
            db.flush()
            ensure_artist_slug(db, treasury_artist, name_source=TREASURY_ARTIST_NAME)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                treasury_artist = get_treasury_artist(db)
    else:
        changed = False
        if treasury_artist.name != TREASURY_ARTIST_NAME:
            treasury_artist.name = TREASURY_ARTIST_NAME
            update_artist_slug(db, treasury_artist, name_source=TREASURY_ARTIST_NAME)
            changed = True
        if not treasury_artist.is_system:
            treasury_artist.is_system = True
            changed = True
        if changed:
            ensure_artist_slug(db, treasury_artist, name_source=treasury_artist.name)
            db.commit()

    if treasury_artist is None:
        raise RuntimeError("Treasury artist missing — system invariant broken")
    ensure_artist_slug(db, treasury_artist, name_source=treasury_artist.name)

    treasury_song = (
        db.query(Song)
        .filter(Song.system_key == TREASURY_SONG_SYSTEM_KEY)
        .one_or_none()
    )
    if treasury_song is None:
        legacy_song = (
            db.query(Song)
            .filter(
                Song.artist_id == treasury_artist.id,
                Song.title == TREASURY_SONG_TITLE,
            )
            .one_or_none()
        )
        if legacy_song is not None:
            legacy_song.system_key = TREASURY_SONG_SYSTEM_KEY
            legacy_song.is_system = True
            legacy_song.artist_id = treasury_artist.id
            treasury_song = legacy_song
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                treasury_song = (
                    db.query(Song)
                    .filter(Song.system_key == TREASURY_SONG_SYSTEM_KEY)
                    .one_or_none()
                )
        else:
            treasury_song = Song(
                title=TREASURY_SONG_TITLE,
                system_key=TREASURY_SONG_SYSTEM_KEY,
                artist_id=treasury_artist.id,
                is_system=True,
            )
            db.add(treasury_song)
            db.flush()
            ensure_song_slug(db, treasury_song, title_source=TREASURY_SONG_TITLE)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                treasury_song = (
                    db.query(Song)
                    .filter(Song.system_key == TREASURY_SONG_SYSTEM_KEY)
                    .one_or_none()
                )
    else:
        changed = False
        if treasury_song.artist_id != treasury_artist.id:
            treasury_song.artist_id = treasury_artist.id
            changed = True
        if treasury_song.title != TREASURY_SONG_TITLE:
            treasury_song.title = TREASURY_SONG_TITLE
            update_song_slug(db, treasury_song, title_source=TREASURY_SONG_TITLE)
            changed = True
        if not treasury_song.is_system:
            treasury_song.is_system = True
            changed = True
        if changed:
            ensure_song_slug(db, treasury_song, title_source=treasury_song.title)
            db.commit()

    if treasury_song is None:
        raise RuntimeError("Treasury song missing — system invariant broken")
    ensure_song_slug(db, treasury_song, title_source=treasury_song.title)

    artist_count = db.query(Artist).filter(Artist.system_key == TREASURY_ARTIST_SYSTEM_KEY).count()
    song_count = db.query(Song).filter(Song.system_key == TREASURY_SONG_SYSTEM_KEY).count()
    if artist_count != 1 or song_count != 1:
        raise RuntimeError("Treasury uniqueness invariant broken")

    return treasury_artist, treasury_song


def get_treasury_song(db):
    treasury_artist = get_treasury_artist(db)
    if not treasury_artist:
        raise RuntimeError("Treasury artist missing")

    song = (
        db.query(Song)
        .filter(
            Song.system_key == TREASURY_SONG_SYSTEM_KEY,
        )
        .one_or_none()
    )
    if song and song.artist_id != treasury_artist.id:
        raise RuntimeError("Treasury song linked to wrong artist")
    return song


def calculate_user_distribution(user_id: int) -> list[dict]:
    db = SessionLocal()

    try:
        balance = db.query(UserBalance).filter_by(user_id=user_id).first()

        if not balance:
            return []

        aggregates = db.query(ListeningAggregate).filter_by(user_id=user_id).all()

        artist_pool = float(balance.monthly_amount) * ARTIST_SHARE
        pool_cents = int(round(artist_pool * 100))

        total_weighted = sum(float(a.weighted_duration or 0) for a in aggregates)
        total_raw = sum(float(a.total_duration or 0) for a in aggregates)

        mode = "weighted"
        denominator = total_weighted
        value_getter = lambda agg: float(agg.weighted_duration or 0)

        if total_weighted > EPSILON:
            mode = "weighted"
            denominator = total_weighted
            value_getter = lambda agg: float(agg.weighted_duration or 0)
        elif total_raw > EPSILON:
            mode = "raw_fallback"
            denominator = total_raw
            value_getter = lambda agg: float(agg.total_duration or 0)
        else:
            treasury_artist, _ = ensure_treasury_entities(db)
            treasury_song = get_treasury_song(db)
            if treasury_song is None:
                raise RuntimeError("Treasury song missing — system invariant broken")
            if pool_cents < 0:
                raise RuntimeError("Invalid pool")
            print(f"[PAYOUT MODE] user={user_id} mode=treasury_fallback")
            distribution = [
                {
                    "song_id": treasury_song.id,
                    "artist_id": treasury_artist.id,
                    "share": 1.0,
                    "cents": pool_cents,
                    "mode": "treasury_fallback",
                }
            ]
            total_distributed_cents = sum(entry["cents"] for entry in distribution)
            if total_distributed_cents != pool_cents:
                raise RuntimeError(
                    f"Conservation error (cents mismatch): distributed={total_distributed_cents}, pool={pool_cents}"
                )
            for entry in distribution:
                entry["payout"] = entry["cents"] / 100.0
            return distribution

        print(f"[PAYOUT MODE] user={user_id} mode={mode}")
        provisional = []
        for idx, a in enumerate(aggregates):
            share = value_getter(a) / denominator
            exact_cents = share * pool_cents
            base_cents = int(math.floor(exact_cents))
            remainder = exact_cents - base_cents
            tie_song_id = int(a.song_id) if a.song_id is not None else 10**18
            provisional.append(
                {
                    "idx": idx,
                    "song_id": a.song_id,
                    "share": share,
                    "base_cents": base_cents,
                    "remainder": remainder,
                    "tie_song_id": tie_song_id,
                    "extra_cent": 0,
                }
            )

        assigned_cents = sum(item["base_cents"] for item in provisional)
        leftover_cents = pool_cents - assigned_cents
        if leftover_cents < 0:
            raise RuntimeError("Conservation error in payout distribution")

        if leftover_cents > 0:
            ranked = sorted(
                provisional,
                key=lambda item: (-item["remainder"], item["tie_song_id"], item["idx"]),
            )
            for i in range(leftover_cents):
                ranked[i]["extra_cent"] += 1

        entries = []
        for item in provisional:
            payout_cents = int(item["base_cents"]) + int(item["extra_cent"])
            entries.append(
                {
                    "song_id": item["song_id"],
                    "share": round(float(item["share"]), 4),
                    "cents": payout_cents,
                    "mode": mode,
                }
            )

        total_distributed_cents = sum(entry["cents"] for entry in entries)
        if total_distributed_cents != pool_cents:
            raise RuntimeError(
                f"Conservation error (cents mismatch): distributed={total_distributed_cents}, pool={pool_cents}"
            )
        for entry in entries:
            entry["payout"] = entry["cents"] / 100.0
        distribution = entries
        return distribution

    finally:
        db.close()
