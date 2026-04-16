"""Catégories Jeu Vidéo Easycash (slugs de bons-plans.easycash.fr).

Ces slugs sont utilisés comme chemins relatifs : https://bons-plans.easycash.fr/<slug>[?page=N]
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Category:
    slug: str        # ex: "consoles/sony"
    label: str       # ex: "Consoles Sony"
    platform: str | None = None  # PS5, PS4, Switch, etc., si spécifique


CATEGORIES: tuple[Category, ...] = (
    # Consoles
    Category("consoles", "Consoles (toutes)"),
    Category("consoles/sony", "Consoles Sony", "Sony"),
    Category("consoles/nintendo", "Consoles Nintendo", "Nintendo"),
    Category("consoles/microsoft", "Consoles Microsoft", "Microsoft"),
    Category("consoles/manettes-accessoires", "Manettes & accessoires"),
    # Jeux
    Category("jeux-video", "Jeux vidéo (tous)"),
    Category("jeux-video/sony", "Jeux Sony", "Sony"),
    Category("jeux-video/nintendo", "Jeux Nintendo", "Nintendo"),
    Category("jeux-video/microsoft", "Jeux Microsoft", "Microsoft"),
    # Rétro
    Category("retrogaming/consoles-retro", "Consoles rétro"),
    Category("retrogaming/jeux-retro", "Jeux rétro"),
)


CATEGORIES_BY_SLUG: dict[str, Category] = {c.slug: c for c in CATEGORIES}


def get(slug: str) -> Category | None:
    return CATEGORIES_BY_SLUG.get(slug)
