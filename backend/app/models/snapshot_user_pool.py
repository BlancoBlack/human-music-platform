from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Integer, UniqueConstraint

from app.core.database import Base


class SnapshotUserPool(Base):
    __tablename__ = "snapshot_user_pools"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(
        Integer, ForeignKey("payout_input_snapshots.id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user_pool_cents = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("snapshot_id", "user_id", name="uq_snapshot_user_pools_snapshot_user"),
        CheckConstraint(
            "user_pool_cents >= 0",
            name="ck_snapshot_user_pools_user_pool_cents_non_negative",
        ),
    )

