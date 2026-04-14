from __future__ import annotations

from app.models.song import (
    SONG_STATE_DRAFT,
    SONG_STATE_ECONOMY_READY,
    SONG_STATE_MEDIA_READY,
    SONG_STATE_METADATA_READY,
    SONG_STATE_READY_FOR_RELEASE,
    Song,
)


class SongStateTransitionError(ValueError):
    """Raised when a requested song state transition is not allowed."""


_STATE_ORDER = [
    SONG_STATE_DRAFT,
    SONG_STATE_MEDIA_READY,
    SONG_STATE_METADATA_READY,
    SONG_STATE_ECONOMY_READY,
    SONG_STATE_READY_FOR_RELEASE,
]

_ALLOWED_DIRECT_TRANSITIONS: dict[str, set[str]] = {
    SONG_STATE_DRAFT: {SONG_STATE_MEDIA_READY},
    SONG_STATE_MEDIA_READY: {SONG_STATE_METADATA_READY},
    SONG_STATE_METADATA_READY: {SONG_STATE_ECONOMY_READY},
    SONG_STATE_ECONOMY_READY: {SONG_STATE_READY_FOR_RELEASE},
    SONG_STATE_READY_FOR_RELEASE: set(),
}


def _normalize_state(raw: str | None) -> str:
    s = str(raw or "").strip()
    return s or SONG_STATE_DRAFT


def _state_rank(state: str) -> int:
    try:
        return _STATE_ORDER.index(state)
    except ValueError as exc:
        raise SongStateTransitionError(f"Unknown song state: {state!r}") from exc


def can_transition_song_state(current: str, target: str) -> bool:
    cur = _normalize_state(current)
    tgt = _normalize_state(target)
    if cur == tgt:
        return True
    return tgt in _ALLOWED_DIRECT_TRANSITIONS.get(cur, set())


def transition_song_state(song: Song, target_state: str) -> None:
    cur = _normalize_state(song.state)
    tgt = _normalize_state(target_state)
    if not can_transition_song_state(cur, tgt):
        raise SongStateTransitionError(
            f"Invalid song state transition: {cur!r} -> {tgt!r}"
        )
    song.state = tgt


def advance_song_state(song: Song, target_state: str) -> None:
    """
    Advance across intermediate states using only allowed direct transitions.
    Backward moves are not allowed.
    """
    cur = _normalize_state(song.state)
    tgt = _normalize_state(target_state)
    if cur == tgt:
        return
    cur_rank = _state_rank(cur)
    tgt_rank = _state_rank(tgt)
    if tgt_rank < cur_rank:
        raise SongStateTransitionError(
            f"Backward song state transition not allowed: {cur!r} -> {tgt!r}"
        )
    for next_state in _STATE_ORDER[cur_rank + 1 : tgt_rank + 1]:
        transition_song_state(song, next_state)


def target_state_from_upload_status(upload_status: str | None) -> str:
    """
    Backward-compatible upload_status -> song.state mapping.
    """
    status = str(upload_status or "").strip().lower()
    if status in {"ready", "published"}:
        return SONG_STATE_READY_FOR_RELEASE
    if status in {"audio_uploaded", "cover_uploaded", "uploaded"}:
        return SONG_STATE_MEDIA_READY
    return SONG_STATE_DRAFT


def sync_song_state_from_upload_status(song: Song) -> None:
    """
    Non-strict compatibility sync that only moves state forward.
    """
    desired = target_state_from_upload_status(song.upload_status)
    current = _normalize_state(song.state)
    if _state_rank(desired) >= _state_rank(current):
        advance_song_state(song, desired)
