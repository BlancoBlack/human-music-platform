"""Append-only signals when playlist track order changes (ingest / future discovery)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer

from app.core.database import Base


class PlaylistReorderEvent(Base):
    """
    One row per song whose ``position`` changed after a successful reorder.
    ``playlist_updated_at`` is the playlist row's ``updated_at`` immediately after that
    reorder (post-mutation snapshot). Discovery may consume a weak runtime aggregate;
    no payout or listening-ingest linkage.
    """

    __tablename__ = "playlist_reorder_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    playlist_id = Column(
        Integer,
        ForeignKey("playlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    song_id = Column(
        Integer,
        ForeignKey("songs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_position = Column(Integer, nullable=False)
    new_position = Column(Integer, nullable=False)
    delta_position = Column(Integer, nullable=False)
    playlist_updated_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
