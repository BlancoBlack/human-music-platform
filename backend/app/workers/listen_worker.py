import logging

from app.core.database import SessionLocal
from app.models.global_listening_aggregate import GlobalListeningAggregate
from app.models.listening_aggregate import ListeningAggregate
from app.models.listening_event import ListeningEvent

logger = logging.getLogger(__name__)

# Phase 2: worker is the sole writer of GlobalListeningAggregate (raw total_duration).
ENABLE_WORKER_GLOBAL_UPDATE = True


def process_listening_event(event_id: int) -> None:
    db = SessionLocal()

    try:
        event = db.query(ListeningEvent).filter(ListeningEvent.id == event_id).first()
        if event is None:
            return
        if event.processed:
            return

        # total_duration (economic model): only valid events contribute.
        if event.is_valid:
            duration = float(event.validated_duration or 0)
        else:
            duration = 0.0

        aggregate = (
            db.query(ListeningAggregate)
            .filter(
                ListeningAggregate.user_id == event.user_id,
                ListeningAggregate.song_id == event.song_id,
            )
            .first()
        )

        if aggregate is None:
            aggregate = ListeningAggregate(user_id=event.user_id, song_id=event.song_id, total_duration=0)
            db.add(aggregate)

        aggregate.total_duration += float(duration)

        # weighted_duration (economic model): only valid events contribute.
        if event.is_valid:
            weighted = float(event.validated_duration or 0) * float(event.weight or 0)
        else:
            weighted = 0.0
        aggregate.weighted_duration = float(aggregate.weighted_duration or 0)
        aggregate.weighted_duration += weighted

        # GlobalListeningAggregate: sum of validated_duration for valid listens only (no weighting).
        if ENABLE_WORKER_GLOBAL_UPDATE:
            if event.is_valid:
                global_increment = float(event.validated_duration or 0)
            else:
                global_increment = 0.0
            global_delta = float(global_increment)
            global_agg = (
                db.query(GlobalListeningAggregate)
                .filter_by(song_id=event.song_id)
                .first()
            )
            if global_agg is None:
                global_agg = GlobalListeningAggregate(
                    song_id=event.song_id,
                    total_duration=global_delta,
                )
                db.add(global_agg)
            else:
                global_agg.total_duration += global_delta

        event.processed = True
        logger.info(
            "listen_event_processed",
            extra={
                "correlation_id": event.correlation_id,
                "event_id": event.id,
                "user_id": event.user_id,
                "song_id": event.song_id,
                "is_valid": event.is_valid,
                "validated_duration": event.validated_duration,
                "weight": event.weight,
            },
        )
        db.commit()

    finally:
        db.close()

