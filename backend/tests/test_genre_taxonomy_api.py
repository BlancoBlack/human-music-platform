"""Smoke tests for genre taxonomy endpoints and song genre fields."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_get_genres_ordered_and_slugs():
    with TestClient(app) as client:
        r = client.get("/genres")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 27
        assert data[0]["slug"] == "electronic"
        assert data[0]["name"] == "Electronic"
        assert all("id" in x and "name" in x and "slug" in x for x in data)


def test_get_subgenres_scoped():
    with TestClient(app) as client:
        genres = client.get("/genres").json()
        electronic = next(g for g in genres if g["slug"] == "electronic")
        r = client.get(f"/genres/{electronic['id']}/subgenres")
        assert r.status_code == 200
        subs = r.json()
        assert len(subs) >= 5
        assert all("slug" in s for s in subs)
        names = {s["name"] for s in subs}
        assert "House" in names
        assert "Afro House" in names


def test_get_subgenres_unknown_genre():
    with TestClient(app) as client:
        assert client.get("/genres/999999/subgenres").status_code == 404
