"""Unit tests for taxonomy slug helpers."""

from __future__ import annotations

import pytest

from app.utils.slugify import allocate_unique_slug, slugify


def test_hip_hop_rap_example():
    assert slugify("Hip-hop / Rap") == "hip-hop-rap"


def test_drum_and_bass():
    assert slugify("Drum & Bass") == "drum-and-bass"


def test_no_double_dashes():
    assert "--" not in slugify("a  /  b")
    assert slugify("a  /  b") == "a-b"


def test_no_trailing_dash():
    assert not slugify("hello-").endswith("-")
    assert slugify("hello-") == "hello"


def test_multiple_separators_collapsed():
    assert slugify("one...two") == "one-two"


def test_empty_and_whitespace():
    assert slugify("") == "unknown"
    assert slugify("   ") == "unknown"


def test_allocate_unique_slug_collision():
    used: set[str] = set()
    assert allocate_unique_slug("foo", used) == "foo"
    assert allocate_unique_slug("foo", used) == "foo-2"
    assert allocate_unique_slug("foo", used) == "foo-3"


def test_unknown_base_collision():
    used: set[str] = {"unknown"}
    assert allocate_unique_slug("unknown", used) == "unknown-2"
