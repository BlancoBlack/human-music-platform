from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from app.models.release import RELEASE_STATE_PUBLISHED
from app.models.song import SONG_STATE_READY_FOR_RELEASE
from app.services.onboarding_state_service import (
    COMPLETED,
    DISCOVERY_STARTED,
    PREFERENCES_SET,
    REGISTERED,
)

# Import for SQLAlchemy insert listeners (artist/release/song slug allocation).
from app.services import slug_service as _slug_service  # noqa: F401

WALLET_ADDRESS: Final[str] = "APQVRSIZTCOOHLVLFOTZAEFPO3VNA5DHXBQNGUQARQP2EBWWLDMKUMNKIA"
MASTER_REL_PATH: Final[str] = "uploads/songs/seed_master.wav"
COVER_REL_PATH: Final[str] = "uploads/covers/seed_cover.png"
CORE_BATCH_ANTIFRAUD: Final[str] = "policy:seed_system_v1"

ARTIST_NAMES: Final[list[str]] = [
    "Marina Herlop",
    "Wesphere",
    "Tarta Relena",
    "Mina Qiu",
    "Fast Boo",
    "El Noi De Tona",
    "Drap Brut",
    "Aguita Fresca",
    "Hi.Mo",
    "Kora Baz",
]

USER_PROFILES: Final[list[dict[str, object]]] = [
    {"first": "Oliver", "last": "Stone", "onboarding_step": COMPLETED, "onboarding_completed": True},
    {"first": "Emma", "last": "Bennett", "onboarding_step": DISCOVERY_STARTED, "onboarding_completed": False},
    {"first": "Liam", "last": "Carter", "onboarding_step": COMPLETED, "onboarding_completed": True},
    {"first": "Chloe", "last": "Baker", "onboarding_step": PREFERENCES_SET, "onboarding_completed": False},
    {"first": "Noah", "last": "Ward", "onboarding_step": COMPLETED, "onboarding_completed": True},
    {"first": "Mia", "last": "Parker", "onboarding_step": DISCOVERY_STARTED, "onboarding_completed": False},
    {"first": "Ethan", "last": "Foster", "onboarding_step": COMPLETED, "onboarding_completed": True},
    {"first": "Ruby", "last": "Cooper", "onboarding_step": REGISTERED, "onboarding_completed": False},
    {"first": "Lucas", "last": "Hayes", "onboarding_step": COMPLETED, "onboarding_completed": True},
    {"first": "Ava", "last": "Turner", "onboarding_step": PREFERENCES_SET, "onboarding_completed": False},
]


@dataclass(frozen=True)
class SeedScale:
    slug: str
    listens_per_user_min: int
    listens_per_user_max: int
    max_repeat_per_user_song: int


SEED_SCALES: Final[dict[str, SeedScale]] = {
    "small": SeedScale("small", 30, 55, 2),
    "medium": SeedScale("medium", 80, 140, 3),
    "large": SeedScale("large", 150, 240, 4),
}


def release_date_for_slot(artist_idx: int, slot: int) -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(days=artist_idx * 11 + slot * 30 + 3)


def song_state() -> str:
    return SONG_STATE_READY_FOR_RELEASE


def release_state() -> str:
    return RELEASE_STATE_PUBLISHED
