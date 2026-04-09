from sqlalchemy import CheckConstraint, Column, Float, ForeignKey, Integer, UniqueConstraint

from app.core.database import Base


class SongArtistSplit(Base):
    __tablename__ = "song_artist_splits"
    __table_args__ = (
        CheckConstraint(
            "share > 0 AND share <= 1",
            name="ck_song_artist_splits_share_range",
        ),
        CheckConstraint(
            "split_bps >= 0 AND split_bps <= 10000",
            name="ck_song_artist_splits_split_bps_range",
        ),
        UniqueConstraint(
            "song_id",
            "artist_id",
            name="uq_song_artist_splits_song_artist",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    song_id = Column(Integer, ForeignKey("songs.id"), nullable=False)
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False)
    share = Column(Float, nullable=False)  # e.g. 0.7; must sum to 1.0 per song (app-enforced)
    split_bps = Column(Integer, nullable=False)  # basis points; must sum to 10000 per song (app-enforced)
