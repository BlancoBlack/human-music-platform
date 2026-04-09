from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
from typing import DefaultDict, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from app.core.database import SessionLocal
from app.economics.policies import get_policy
from app.models.listening_event import ListeningEvent
from app.models.payout_batch import PayoutBatch
from app.models.payout_input_snapshot import PayoutInputSnapshot
from app.models.snapshot_listening_input import SnapshotListeningInput
from app.models.snapshot_user_pool import SnapshotUserPool
from app.models.user_balance import UserBalance


def build_snapshot(
    batch_id: int, period_start_at: datetime, period_end_at: datetime, policy_id: str = "v1"
) -> int:
    """
    MVP snapshot build for payout engine v2.

    Strict integer-only snapshot units:
    - user_pool_cents = int(round(monthly_amount * policy.artist_share * 100))
    - raw_units_i = int(round(validated_duration * 1000))
    - qualified_units_i = int(round(validated_duration * weight * 1000))

    Economic policy encoded by this snapshot (single source of truth):
    - artist share reduction is applied at snapshot build time
    - antifraud is encoded via ListeningEvent.is_valid / validated_duration
    - weighting is encoded via ListeningEvent.weight (exp(-policy.weight_decay_lambda * repeats))
    """
    db = SessionLocal()

    try:
        policy = get_policy(policy_id)
        batch = db.query(PayoutBatch).filter(PayoutBatch.id == batch_id).first()
        if batch is None:
            raise RuntimeError(f"payout_batches not found for batch_id={batch_id}")
        if batch.status != "draft":
            raise RuntimeError(
                f"build_snapshot requires batch status='draft', got '{batch.status}'"
            )
        if batch.snapshot_id is not None:
            raise RuntimeError("Batch already has a snapshot")

        # Step 1 — CREATE SNAPSHOT HEADER
        source_time_cutoff = datetime.utcnow()
        # Traceability: these versions identify the economic policy used
        # to generate this snapshot (money base, antifraud, weighting).
        snapshot = PayoutInputSnapshot(
            batch_id=batch_id,
            period_start_at=period_start_at,
            period_end_at=period_end_at,
            currency="USD",
            calculation_version="v2",
            antifraud_version=(
                f"policy:{policy.policy_id}:min={policy.min_listen_seconds}:"
                f"ratio={policy.full_play_threshold_ratio}:daily_cap={policy.daily_cap}"
            ),
            listening_aggregation_version=(
                f"policy:{policy.policy_id}:lambda={policy.weight_decay_lambda}:"
                f"repeat_window_h={policy.repeat_window_hours}"
            ),
            policy_id=policy.policy_id,
            policy_artist_share=float(policy.artist_share),
            policy_weight_decay_lambda=float(policy.weight_decay_lambda),
            policy_json=json.dumps(policy.to_dict(), sort_keys=True),
            source_time_cutoff=source_time_cutoff,
            snapshot_state="draft",
        )
        db.add(snapshot)
        db.flush()  # assign snapshot.id without committing
        snapshot_id = snapshot.id

        # Step 2 — LOAD USERS
        users = (
            db.query(UserBalance)
            .filter(UserBalance.monthly_amount.isnot(None))
            .filter(UserBalance.monthly_amount > 0)
            .order_by(UserBalance.user_id.asc())
            .all()
        )

        total_user_pool_cents = 0
        for ub in users:
            monthly_amount = float(ub.monthly_amount or 0.0)
            if monthly_amount <= 0:
                continue
            # V1-compatible money base: snapshot stores only artist-share pool.
            user_pool_cents = int(round(monthly_amount * float(policy.artist_share) * 100))
            if user_pool_cents < 0:
                raise RuntimeError("Invalid user_pool_cents computed (< 0)")
            db.add(
                SnapshotUserPool(
                    snapshot_id=snapshot_id,
                    user_id=int(ub.user_id),
                    user_pool_cents=user_pool_cents,
                )
            )
            total_user_pool_cents += user_pool_cents

        db.flush()

        # Step 3 — LOAD LISTENING EVENTS
        # Only validated (is_valid=True) events contribute to snapshot listening inputs.
        events = (
            db.query(ListeningEvent)
            .filter(ListeningEvent.is_valid.is_(True))
            .filter(ListeningEvent.song_id.isnot(None))
            .filter(ListeningEvent.timestamp.isnot(None))
            .filter(ListeningEvent.timestamp >= period_start_at)
            .filter(ListeningEvent.timestamp < period_end_at)
            .filter(ListeningEvent.created_at <= source_time_cutoff)
            .order_by(
                ListeningEvent.user_id.asc(),
                ListeningEvent.song_id.asc(),
                ListeningEvent.id.asc(),
            )
            .all()
        )

        n_users = len(users)
        n_events = len(events)

        # Step 4 — AGGREGATE PER (user_id, song_id)
        acc: DefaultDict[Tuple[int, int], dict[str, int]] = defaultdict(
            lambda: {"raw_units": 0, "qualified_units": 0}
        )

        # Step 5 — INTEGER CONVERSION (CRITICAL)
        for e in events:
            user_id = int(e.user_id)
            song_id = int(e.song_id)

            # V1 semantic mapping:
            # - raw_units_i uses validated_duration (post-antifraud duration gate)
            # - qualified_units_i uses validated_duration * weight
            validated_duration = float(e.validated_duration or 0.0)
            weight = float(e.weight or 0.0)

            # Deterministic rounding boundary for float -> integer conversion.
            # We round per event to ensure stable integer totals across runs.
            raw_units_increment = int(round(validated_duration * 1000))
            qualified_units_increment = int(round(validated_duration * weight * 1000))

            if raw_units_increment < 0 or qualified_units_increment < 0:
                raise RuntimeError("Computed snapshot units must be >= 0")

            key = (user_id, song_id)
            acc[key]["raw_units"] += raw_units_increment
            acc[key]["qualified_units"] += qualified_units_increment

        # Step 6 — INSERT snapshot_listening_inputs
        total_raw_units = 0
        total_qualified_units = 0
        for (user_id, song_id) in sorted(acc.keys()):
            raw_units_i = int(acc[(user_id, song_id)]["raw_units"])
            qualified_units_i = int(acc[(user_id, song_id)]["qualified_units"])

            total_raw_units += raw_units_i
            total_qualified_units += qualified_units_i

            if raw_units_i < 0 or qualified_units_i < 0:
                raise RuntimeError("Snapshot listening units must be >= 0")

            db.add(
                SnapshotListeningInput(
                    snapshot_id=snapshot_id,
                    user_id=user_id,
                    song_id=song_id,
                    raw_units_i=raw_units_i,
                    qualified_units_i=qualified_units_i,
                )
            )

        db.flush()

        # Step 8 — COMPUTE TOTALS
        # (user pool totals were computed while inserting SnapshotUserPool)
        total_user_pool = int(total_user_pool_cents)
        total_raw_units = int(total_raw_units)
        total_qualified_units = int(total_qualified_units)

        # Step 9 — UPDATE SNAPSHOT HEADER
        snapshot.snapshot_user_pool_sum_cents = total_user_pool
        snapshot.snapshot_listening_raw_units_sum = total_raw_units
        snapshot.snapshot_listening_qualified_units_sum = total_qualified_units

        db.flush()

        # Step 10 — VALIDATION (MUST PASS)
        # 10.1 No duplicate (snapshot_id, user_id)
        user_pool_rows = (
            db.query(SnapshotUserPool.user_id)
            .filter(SnapshotUserPool.snapshot_id == snapshot_id)
            .all()
        )
        user_ids = [int(r[0]) for r in user_pool_rows]
        if len(user_ids) != len(set(user_ids)):
            raise RuntimeError("Duplicate user_id in snapshot_user_pools")

        # 10.2 No duplicate (snapshot_id, user_id, song_id)
        listening_rows = (
            db.query(SnapshotListeningInput.user_id, SnapshotListeningInput.song_id)
            .filter(SnapshotListeningInput.snapshot_id == snapshot_id)
            .all()
        )
        pairs = [(int(u), int(s)) for u, s in listening_rows]
        if len(pairs) != len(set(pairs)):
            raise RuntimeError("Duplicate (user_id, song_id) in snapshot_listening_inputs")

        # 10.3 All user_pool_cents >= 0
        bad_user_pools = (
            db.query(SnapshotUserPool.id)
            .filter(
                SnapshotUserPool.snapshot_id == snapshot_id,
                SnapshotUserPool.user_pool_cents < 0,
            )
            .all()
        )
        if bad_user_pools:
            raise RuntimeError("Found user_pool_cents < 0")

        # 10.4 All units >= 0
        bad_units = (
            db.query(SnapshotListeningInput.id)
            .filter(
                SnapshotListeningInput.snapshot_id == snapshot_id,
            )
            .filter(
                (SnapshotListeningInput.raw_units_i < 0)
                | (SnapshotListeningInput.qualified_units_i < 0)
            )
            .all()
        )
        if bad_units:
            raise RuntimeError("Found negative snapshot listening units")

        # Step 10.5 — SNAPSHOT SELF-CONSISTENCY CHECK (DB SUMS)
        db_total_user_pool = (
            db.query(func.sum(SnapshotUserPool.user_pool_cents))
            .filter(SnapshotUserPool.snapshot_id == snapshot_id)
            .scalar()
        )
        db_total_raw_units = (
            db.query(func.sum(SnapshotListeningInput.raw_units_i))
            .filter(SnapshotListeningInput.snapshot_id == snapshot_id)
            .scalar()
        )
        db_total_qualified_units = (
            db.query(func.sum(SnapshotListeningInput.qualified_units_i))
            .filter(SnapshotListeningInput.snapshot_id == snapshot_id)
            .scalar()
        )

        # SQLite returns None for empty sums; normalize to 0.
        db_total_user_pool = int(db_total_user_pool or 0)
        db_total_raw_units = int(db_total_raw_units or 0)
        db_total_qualified_units = int(db_total_qualified_units or 0)

        if db_total_user_pool != int(snapshot.snapshot_user_pool_sum_cents or 0):
            raise RuntimeError("Snapshot self-consistency failed: user_pool_cents sum mismatch")
        if db_total_raw_units != int(snapshot.snapshot_listening_raw_units_sum or 0):
            raise RuntimeError("Snapshot self-consistency failed: raw_units sum mismatch")
        if (
            db_total_qualified_units
            != int(snapshot.snapshot_listening_qualified_units_sum or 0)
        ):
            raise RuntimeError(
                "Snapshot self-consistency failed: qualified_units sum mismatch"
            )

        # Step 11 — SEAL SNAPSHOT
        snapshot.snapshot_state = "sealed"
        snapshot.sealed_at = datetime.utcnow()
        db.add(snapshot)

        # Bind batch -> snapshot (explicit, deterministic).
        batch.snapshot_id = int(snapshot_id)
        batch.status = "calculating"
        db.add(batch)

        db.commit()

        # Optional debug log (low cost).
        print(f"[SNAPSHOT BUILT] id={snapshot_id} users={n_users} events={n_events}")

        return snapshot_id

    except IntegrityError as e:
        db.rollback()
        raise RuntimeError(f"Snapshot build failed due to integrity error: {e}") from e
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

