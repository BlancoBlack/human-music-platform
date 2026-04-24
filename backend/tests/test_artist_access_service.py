from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.artist import Artist
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.song import Song
from app.models.user import User
from app.models.user_role import UserRole
from app.services.artist_access_service import (
    can_upload_song,
    can_edit_artist,
    create_artist_for_user,
    get_user_owned_artists,
)


def _seed_permissions(db) -> None:
    db.add_all(
        [
            Role(name="admin"),
            Role(name="editor_any"),
            Role(name="editor_own"),
            Permission(name="admin_full_access"),
            Permission(name="edit_any_artist"),
            Permission(name="edit_own_artist"),
        ]
    )
    db.flush()
    roles = {row.name: int(row.id) for row in db.query(Role).all()}
    perms = {row.name: int(row.id) for row in db.query(Permission).all()}
    db.add_all(
        [
            RolePermission(
                role_id=roles["admin"],
                permission_id=perms["admin_full_access"],
            ),
            RolePermission(
                role_id=roles["editor_any"],
                permission_id=perms["edit_any_artist"],
            ),
            RolePermission(
                role_id=roles["editor_own"],
                permission_id=perms["edit_own_artist"],
            ),
        ]
    )
    db.commit()


def _make_user(db, email: str) -> User:
    user = User(
        email=email,
        password_hash="x",
        is_active=True,
        is_email_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_create_artist_for_user_sets_owner_user_id() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        owner = _make_user(db, "owner@example.com")
        artist = create_artist_for_user(db, current_user=owner, name="Owned Artist")
        db.commit()
        db.refresh(artist)
        assert int(artist.owner_user_id) == int(owner.id)
    finally:
        db.close()


def test_can_edit_artist_permission_matrix() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        _seed_permissions(db)
        admin_user = _make_user(db, "admin@example.com")
        any_user = _make_user(db, "any@example.com")
        own_user = _make_user(db, "own@example.com")
        other_user = _make_user(db, "other@example.com")

        db.add_all(
            [
                UserRole(user_id=int(admin_user.id), role="admin"),
                UserRole(user_id=int(any_user.id), role="editor_any"),
                UserRole(user_id=int(own_user.id), role="editor_own"),
            ]
        )
        db.commit()

        owned_artist = Artist(name="Matrix Artist", owner_user_id=int(own_user.id))
        db.add(owned_artist)
        db.commit()
        db.refresh(owned_artist)

        assert can_edit_artist(admin_user, owned_artist, db=db) is True
        assert can_edit_artist(any_user, owned_artist, db=db) is True
        assert can_edit_artist(own_user, owned_artist, db=db) is True
        assert can_edit_artist(other_user, owned_artist, db=db) is False
    finally:
        db.close()


def test_get_user_owned_artists_returns_only_owned_rows() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        owner = _make_user(db, "owned.list@example.com")
        other = _make_user(db, "other.list@example.com")
        db.add_all(
            [
                Artist(name="Owned 1", owner_user_id=int(owner.id)),
                Artist(name="Owned 2", owner_user_id=int(owner.id)),
                Artist(name="Other 1", owner_user_id=int(other.id)),
                Artist(name="No owner", owner_user_id=None),
            ]
        )
        db.commit()
        owned_rows = get_user_owned_artists(int(owner.id), db)
        owned_names = [row.name for row in owned_rows]
        assert owned_names == ["Owned 1", "Owned 2"]
    finally:
        db.close()


def test_can_upload_song_respects_onboarding_state() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        artist_user = _make_user(db, "new.artist@example.com")
        artist_user.onboarding_completed = False
        artist = Artist(name="Upload Cap Artist", owner_user_id=int(artist_user.id))
        db.add(artist)
        db.commit()
        db.refresh(artist)

        assert can_upload_song(artist_user, artist, db=db) is True

        db.add(Song(title="First", artist_id=int(artist.id)))
        db.commit()

        assert can_upload_song(artist_user, artist, db=db) is False

        artist_user.onboarding_completed = True
        db.commit()
        assert can_upload_song(artist_user, artist, db=db) is True
    finally:
        db.close()
