from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class PayoutSettlement(Base):
    """
    One row per (payout batch, artist): on-chain settlement + auditable breakdown.
    """

    __tablename__ = "payout_settlements"

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("payout_batches.id"), nullable=False, index=True)
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False, index=True)

    total_cents = Column(Integer, nullable=False)
    breakdown_json = Column(Text, nullable=False)
    breakdown_hash = Column(String(64), nullable=False, index=True)
    splits_digest = Column(String(64), nullable=True, index=True)

    destination_wallet = Column(String(255), nullable=True)

    algorand_tx_id = Column(String(128), nullable=True)
    execution_status = Column(String(32), nullable=False, default="pending", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    failure_reason = Column(Text, nullable=True)

    submitted_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    batch = relationship("PayoutBatch", foreign_keys=[batch_id])
    artist = relationship("Artist", foreign_keys=[artist_id])

    __table_args__ = (
        UniqueConstraint("batch_id", "artist_id", name="uq_payout_settlements_batch_artist"),
        CheckConstraint("total_cents >= 0", name="ck_payout_settlements_total_non_negative"),
        CheckConstraint("attempt_count >= 0", name="ck_payout_settlements_attempt_non_negative"),
        CheckConstraint(
            "execution_status IN ('pending', 'submitted', 'confirmed', 'failed')",
            name="ck_payout_settlements_execution_status",
        ),
    )
