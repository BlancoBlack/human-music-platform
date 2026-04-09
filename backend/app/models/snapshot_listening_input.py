from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Integer, UniqueConstraint

from app.core.database import Base


class SnapshotListeningInput(Base):
    __tablename__ = "snapshot_listening_inputs"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(
        Integer, ForeignKey("payout_input_snapshots.id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    song_id = Column(Integer, ForeignKey("songs.id"), nullable=False, index=True)

    raw_units_i = Column(BigInteger, nullable=False)
    qualified_units_i = Column(BigInteger, nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "user_id",
            "song_id",
            name="uq_snapshot_listening_inputs_snapshot_user_song",
        ),
        CheckConstraint(
            "raw_units_i >= 0",
            name="ck_snapshot_listening_inputs_raw_units_non_negative",
        ),
        CheckConstraint(
            "qualified_units_i >= 0",
            name="ck_snapshot_listening_inputs_qualified_units_non_negative",
        ),
    )

