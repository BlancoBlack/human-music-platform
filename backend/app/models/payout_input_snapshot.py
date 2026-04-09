from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.core.database import Base


class PayoutInputSnapshot(Base):
    __tablename__ = "payout_input_snapshots"

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("payout_batches.id"), nullable=False, index=True)

    period_start_at = Column(DateTime, nullable=False)
    period_end_at = Column(DateTime, nullable=False)

    currency = Column(String(3), nullable=False, default="USD")
    calculation_version = Column(String(64), nullable=False, default="v2")
    antifraud_version = Column(String(64), nullable=False, default="v1")
    listening_aggregation_version = Column(String(64), nullable=False, default="v1")
    policy_id = Column(String(64), nullable=False, default="v1", index=True)
    policy_artist_share = Column(Float, nullable=False, default=0.70)
    policy_weight_decay_lambda = Column(Float, nullable=False, default=0.22)
    policy_json = Column(Text, nullable=True)

    source_time_cutoff = Column(DateTime, nullable=False)

    snapshot_state = Column(String(16), nullable=False, default="draft", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    sealed_at = Column(DateTime, nullable=True)

    snapshot_user_pool_sum_cents = Column(BigInteger, nullable=True)
    snapshot_listening_raw_units_sum = Column(BigInteger, nullable=True)
    snapshot_listening_qualified_units_sum = Column(BigInteger, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "period_end_at > period_start_at",
            name="ck_payout_input_snapshots_period_order",
        ),
        CheckConstraint(
            "snapshot_state IN ('draft', 'sealed')",
            name="ck_payout_input_snapshots_state",
        ),
        CheckConstraint(
            "length(currency) = 3",
            name="ck_payout_input_snapshots_currency_len",
        ),
        CheckConstraint(
            "snapshot_user_pool_sum_cents IS NULL OR snapshot_user_pool_sum_cents >= 0",
            name="ck_payout_input_snapshots_user_pool_sum_non_negative",
        ),
        CheckConstraint(
            "snapshot_listening_raw_units_sum IS NULL OR snapshot_listening_raw_units_sum >= 0",
            name="ck_payout_input_snapshots_raw_units_sum_non_negative",
        ),
        CheckConstraint(
            "snapshot_listening_qualified_units_sum IS NULL OR snapshot_listening_qualified_units_sum >= 0",
            name="ck_payout_input_snapshots_qualified_units_sum_non_negative",
        ),
        CheckConstraint(
            "policy_artist_share >= 0 AND policy_artist_share <= 1",
            name="ck_payout_input_snapshots_policy_artist_share_range",
        ),
        CheckConstraint(
            "policy_weight_decay_lambda >= 0",
            name="ck_payout_input_snapshots_policy_weight_decay_non_negative",
        ),
    )

