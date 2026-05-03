"""Parity tests for ``signal_aggregator.compute_signal_contributions`` (discovery ranking)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.services.signal_aggregator import (
    LIKE_BOOST_ALPHA,
    LIKE_CAP,
    LIKE_CAP_ENABLED,
    LIKE_PLAYLIST_CORRELATION_DAMP,
    PLAYLIST_POPULARITY_ALPHA,
    REORDER_BOOST_ALPHA,
    compute_signal_contributions,
)


def _legacy_signal_math(
    playlist_count: int,
    reorder_signal: float,
    *,
    like_count: int = 0,
) -> dict[str, float]:
    """Reference formulas (playlist + reorder + likes) for parity."""
    playlist_signal = math.log1p(int(playlist_count))
    playlist_boost = PLAYLIST_POPULARITY_ALPHA * playlist_signal
    rs = float(reorder_signal)
    reorder_boost = REORDER_BOOST_ALPHA * rs
    pc_i = int(playlist_count)
    lc_i = int(like_count)
    eff = min(lc_i, int(LIKE_CAP)) if LIKE_CAP_ENABLED else lc_i
    like_signal = float(math.log1p(eff))
    like_boost = float(LIKE_BOOST_ALPHA * like_signal)
    if pc_i > 0:
        like_boost = float(like_boost * float(LIKE_PLAYLIST_CORRELATION_DAMP))
    user_signal_score = reorder_boost
    global_signal_score = playlist_boost + like_boost
    signal_score = user_signal_score + global_signal_score
    return {
        "playlist_signal": float(playlist_signal),
        "playlist_boost": float(playlist_boost),
        "like_signal": float(like_signal),
        "like_boost": float(like_boost),
        "reorder_signal": rs,
        "reorder_boost": float(reorder_boost),
        "user_signal_score": float(user_signal_score),
        "global_signal_score": float(global_signal_score),
        "signal_score": float(signal_score),
    }


def _structured_matches_legacy(
    signals: dict[str, Any],
    legacy: dict[str, float],
    *,
    playlist_count: int,
    like_count: int,
) -> None:
    assert signals["global"]["playlist"]["raw"] == int(playlist_count)
    assert signals["global"]["playlist"]["signal"] == pytest.approx(legacy["playlist_signal"])
    assert signals["global"]["playlist"]["boost"] == pytest.approx(legacy["playlist_boost"])
    assert signals["global"]["likes"]["raw"] == int(like_count)
    assert signals["global"]["likes"]["signal"] == pytest.approx(legacy["like_signal"])
    assert signals["global"]["likes"]["boost"] == pytest.approx(legacy["like_boost"])
    assert signals["user"]["reorder"]["signal"] == pytest.approx(legacy["reorder_signal"])
    assert signals["user"]["reorder"]["boost"] == pytest.approx(legacy["reorder_boost"])
    assert signals["total"]["user_signal_score"] == pytest.approx(legacy["user_signal_score"])
    assert signals["total"]["global_signal_score"] == pytest.approx(legacy["global_signal_score"])
    assert signals["total"]["signal_score"] == pytest.approx(legacy["signal_score"])
    assert signals["total"]["signal_score"] == pytest.approx(
        signals["total"]["user_signal_score"] + signals["total"]["global_signal_score"]
    )
    assert signals["total"]["global_signal_score"] == pytest.approx(
        signals["global"]["playlist"]["boost"] + signals["global"]["likes"]["boost"]
    )


@pytest.mark.parametrize(
    "playlist_count,reorder_signal,like_count",
    [
        (0, 0.0, 0),
        (0, 2.5, 0),
        (1, 0.0, 3),
        (3, 1.0, 10),
        (100, 0.6931471805599453, 0),
        (7, -0.5, 50),
        (0, 0.0, 100),
    ],
)
def test_compute_signal_contributions_matches_legacy_formulas(
    playlist_count: int,
    reorder_signal: float,
    like_count: int,
) -> None:
    legacy = _legacy_signal_math(playlist_count, reorder_signal, like_count=like_count)
    got = compute_signal_contributions(
        playlist_count,
        reorder_signal,
        like_count=like_count,
    )
    _structured_matches_legacy(got, legacy, playlist_count=playlist_count, like_count=like_count)


def test_like_signal_ten_matches_formula() -> None:
    got = compute_signal_contributions(0, 0.0, like_count=10)
    expected_signal = math.log1p(min(10, LIKE_CAP))
    assert got["global"]["likes"]["signal"] == pytest.approx(expected_signal)
    assert got["global"]["likes"]["boost"] == pytest.approx(LIKE_BOOST_ALPHA * expected_signal)


def test_total_signal_score_equals_user_plus_global() -> None:
    got = compute_signal_contributions(playlist_count=5, reorder_signal=0.42, like_count=8)
    assert got["total"]["signal_score"] == pytest.approx(
        got["total"]["user_signal_score"] + got["total"]["global_signal_score"]
    )


def test_likes_do_not_change_playlist_or_reorder_sub_boosts() -> None:
    base = compute_signal_contributions(3, 1.1, like_count=0)
    with_likes = compute_signal_contributions(3, 1.1, like_count=99)
    assert with_likes["global"]["playlist"] == base["global"]["playlist"]
    assert with_likes["user"]["reorder"] == base["user"]["reorder"]


def test_playlist_correlation_damp_reduces_like_boost_when_playlist_positive() -> None:
    with_pc = compute_signal_contributions(2, 0.0, like_count=15)
    no_pc = compute_signal_contributions(0, 0.0, like_count=15)
    assert with_pc["global"]["likes"]["raw"] == no_pc["global"]["likes"]["raw"]
    assert with_pc["global"]["likes"]["signal"] == pytest.approx(no_pc["global"]["likes"]["signal"])
    assert with_pc["global"]["likes"]["boost"] == pytest.approx(
        no_pc["global"]["likes"]["boost"] * float(LIKE_PLAYLIST_CORRELATION_DAMP)
    )


def test_score_lines_parity_with_signal_score() -> None:
    base_score = 0.73
    quality_penalty = 0.88
    signals = compute_signal_contributions(4, 1.1, like_count=0)
    signal_score = float(signals["total"]["signal_score"])
    score = float(base_score) * float(quality_penalty) + signal_score
    for_you_score = float(base_score) + signal_score
    legacy_pb = PLAYLIST_POPULARITY_ALPHA * math.log1p(4)
    legacy_rb = REORDER_BOOST_ALPHA * 1.1
    assert score == pytest.approx(base_score * quality_penalty + legacy_pb + legacy_rb)
    assert for_you_score == pytest.approx(base_score + legacy_pb + legacy_rb)
