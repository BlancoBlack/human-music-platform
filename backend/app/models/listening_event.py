from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from datetime import datetime
from app.core.database import Base

class ListeningEvent(Base):
    __tablename__ = "listening_events"
    __table_args__ = (
        Index("ix_listening_events_created_at", "created_at"),
        Index("ix_listening_events_song_id_created_at", "song_id", "created_at"),
        Index("ix_listening_events_user_id_created_at", "user_id", "created_at"),
        Index(
            "ix_listening_events_user_id_song_id_created_at",
            "user_id",
            "song_id",
            "created_at",
        ),
        Index("ix_listening_events_correlation_id", "correlation_id"),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_listening_events_user_idempotency",
        ),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    song_id = Column(Integer)
    session_id = Column(Integer, ForeignKey("listening_sessions.id"))
    weight = Column(Float, default=1.0)
    timestamp = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Developer note: duration is stored as INTEGER (whole seconds) to match the
    # public stream API and analytics thresholds (e.g. duration >= 5). Do not
    # widen to FLOAT/REAL without an explicit product decision and DB migration:
    # fractional seconds may be desired later for antifraud, weighting, or
    # normalization, but that would require coordinated schema + ingestion changes.
    duration = Column(Integer)
    processed = Column(Boolean, default=False, nullable=False)

    # Phase 1 (enrichment only): store economic validation metadata without changing
    # existing aggregation/payout behavior (which currently uses `duration`).
    is_valid = Column(Boolean, default=False, nullable=False)
    validated_duration = Column(Float, default=0.0, nullable=False)
    validation_reason = Column(Text, nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    correlation_id = Column(String(64), nullable=True)