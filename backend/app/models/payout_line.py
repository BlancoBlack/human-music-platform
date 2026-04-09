from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    BigInteger,
    String,
    UniqueConstraint,
)

from app.core.database import Base


class PayoutLine(Base):
    __tablename__ = "payout_lines"

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("payout_batches.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    song_id = Column(Integer, ForeignKey("songs.id"), nullable=False, index=True)
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False, index=True)
    amount_cents = Column(BigInteger, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    line_type = Column(String(32), nullable=False, default="royalty")
    idempotency_key = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "amount_cents >= 0",
            name="ck_payout_lines_amount_non_negative",
        ),
        CheckConstraint(
            "line_type IN ('royalty', 'treasury', 'adjustment')",
            name="ck_payout_lines_line_type",
        ),
        CheckConstraint(
            "length(currency) = 3",
            name="ck_payout_lines_currency_len",
        ),
        UniqueConstraint(
            "batch_id",
            "idempotency_key",
            name="uq_payout_lines_batch_idempotency",
        ),
    )
