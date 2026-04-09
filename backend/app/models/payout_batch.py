from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class PayoutBatch(Base):
    __tablename__ = "payout_batches"

    id = Column(Integer, primary_key=True)
    period_start_at = Column(DateTime, nullable=False)
    period_end_at = Column(DateTime, nullable=False)
    status = Column(String(32), nullable=False, index=True, default="draft")
    currency = Column(String(3), nullable=False, default="USD")
    calculation_version = Column(String(64), nullable=False, default="v2")
    antifraud_version = Column(String(64), nullable=False, default="v1")
    source_snapshot_hash = Column(String(128), nullable=True)
    snapshot_id = Column(
        Integer, ForeignKey("payout_input_snapshots.id"), nullable=True, index=True
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finalized_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "period_end_at > period_start_at",
            name="ck_payout_batches_period_order",
        ),
        CheckConstraint(
            "status IN ('draft', 'calculating', 'finalized', 'posted')",
            name="ck_payout_batches_status",
        ),
        CheckConstraint(
            "length(currency) = 3",
            name="ck_payout_batches_currency_len",
        ),
    )
