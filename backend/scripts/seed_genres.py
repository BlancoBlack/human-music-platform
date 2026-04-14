#!/usr/bin/env python3
"""
Idempotent seed: canonical main genres + subgenres (with slugs).

Run from repo root or ``backend/`` with PYTHONPATH including ``backend``:

    cd backend && PYTHONPATH=. python scripts/seed_genres.py
"""

from __future__ import annotations

from app.core.database import SessionLocal
from app.data.genres import (
    CANONICAL_GENRE_ORDER,
    LEGACY_GENRE_NAMES_BY_SLUG,
    SUBGENRES_BY_GENRE_SLUG,
)
from app.models.genre import Genre
from app.models.subgenre import Subgenre
from app.utils.slugify import allocate_unique_slug, slugify


def _ensure_genre(db, name: str, slug: str) -> str:
    """Returns ``inserted``, ``updated``, or ``unchanged``."""
    g = db.query(Genre).filter(Genre.slug == slug).first()
    if g is not None:
        if g.name != name:
            g.name = name
            return "updated"
        return "unchanged"

    g = db.query(Genre).filter(Genre.name == name).first()
    if g is not None:
        changed = g.slug != slug
        g.slug = slug
        g.name = name
        return "updated" if changed else "unchanged"

    for legacy in LEGACY_GENRE_NAMES_BY_SLUG.get(slug, ()):
        g = db.query(Genre).filter(Genre.name == legacy).first()
        if g is not None:
            g.name = name
            g.slug = slug
            return "updated"

    db.add(Genre(name=name, slug=slug))
    db.flush()
    return "inserted"


def _sync_subgenre(
    db,
    genre_id: int,
    canonical_name: str,
    slug_used: set[str],
) -> str:
    """Returns ``inserted``, ``updated``, or ``unchanged``."""
    existing = (
        db.query(Subgenre)
        .filter(
            Subgenre.genre_id == int(genre_id),
            Subgenre.name == canonical_name,
        )
        .first()
    )
    base = slugify(canonical_name)

    if existing is not None:
        old_slug = existing.slug
        if old_slug and old_slug in slug_used:
            slug_used.discard(old_slug)
        target_slug = allocate_unique_slug(base, slug_used)
        name_changed = existing.name != canonical_name
        slug_changed = existing.slug != target_slug
        if slug_changed:
            existing.slug = target_slug
        if name_changed:
            existing.name = canonical_name
        if slug_changed or name_changed:
            return "updated"
        return "unchanged"

    target_slug = allocate_unique_slug(base, slug_used)
    db.add(
        Subgenre(
            genre_id=int(genre_id),
            name=canonical_name,
            slug=target_slug,
        )
    )
    return "inserted"


def main() -> None:
    db = SessionLocal()
    slug_used: set[str] = set()
    inserted_genres = 0
    updated_genres = 0
    inserted_subgenres = 0
    updated_subgenres = 0
    try:
        for (s,) in db.query(Genre.slug).all():
            if s:
                slug_used.add(str(s))
        for (s,) in db.query(Subgenre.slug).all():
            if s:
                slug_used.add(str(s))
        for _name, gslug in CANONICAL_GENRE_ORDER:
            slug_used.add(gslug)

        genre_rows: list[tuple[Genre, str]] = []
        for name, gslug in CANONICAL_GENRE_ORDER:
            st = _ensure_genre(db, name, gslug)
            if st == "inserted":
                inserted_genres += 1
            elif st == "updated":
                updated_genres += 1
            g = db.query(Genre).filter(Genre.slug == gslug).one()
            genre_rows.append((g, gslug))
        db.flush()

        for g, gslug in genre_rows:
            names = SUBGENRES_BY_GENRE_SLUG.get(gslug, [])
            for display_name in names:
                st = _sync_subgenre(db, int(g.id), display_name, slug_used)
                if st == "inserted":
                    inserted_subgenres += 1
                elif st == "updated":
                    updated_subgenres += 1

        db.commit()
        total_g = db.query(Genre).count()
        total_sg = db.query(Subgenre).count()
        print(
            f"inserted_genres={inserted_genres} "
            f"updated_genres={updated_genres} "
            f"inserted_subgenres={inserted_subgenres} "
            f"updated_subgenres={updated_subgenres} "
            f"(totals: genres={total_g}, subgenres={total_sg})"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
