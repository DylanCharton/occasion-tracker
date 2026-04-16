"""Catégories Jeu Vidéo Easycash (slugs de bons-plans.easycash.fr).

Ces slugs sont utilisés comme chemins relatifs : https://bons-plans.easycash.fr/<slug>[?page=N]
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Category:
    slug: str        # ex: "consoles/sony/ps5"
    label: str       # ex: "Consoles PS5"
    group: str       # ex: "Consoles Sony" — pour grouper dans l'UI
    platform: str | None = None


# --- Catégories larges (toutes plateformes) --------------------------------

_BROAD: tuple[Category, ...] = (
    Category("jeux-video", "Tous les jeux", "Jeux — Tous"),
    Category("consoles", "Toutes les consoles", "Consoles — Toutes"),
    Category("consoles/manettes-accessoires", "Manettes & accessoires", "Accessoires"),
    Category("retrogaming/consoles-retro", "Consoles rétro", "Rétro"),
    Category("retrogaming/jeux-retro", "Jeux rétro", "Rétro"),
)

# --- Jeux par plateforme ---------------------------------------------------

_JEUX_SONY: tuple[Category, ...] = (
    Category("jeux-video/sony", "Jeux Sony (tous)", "Jeux Sony"),
    Category("jeux-video/sony/ps5", "Jeux PS5", "Jeux Sony", "PS5"),
    Category("jeux-video/sony/ps4", "Jeux PS4", "Jeux Sony", "PS4"),
    Category("jeux-video/sony/ps3", "Jeux PS3", "Jeux Sony", "PS3"),
    Category("jeux-video/sony/ps2", "Jeux PS2", "Jeux Sony", "PS2"),
    Category("jeux-video/sony/ps1", "Jeux PS1", "Jeux Sony", "PS1"),
    Category("jeux-video/sony/psp", "Jeux PSP", "Jeux Sony", "PSP"),
    Category("jeux-video/sony/ps-vita", "Jeux PS Vita", "Jeux Sony", "PS Vita"),
)

_JEUX_NINTENDO: tuple[Category, ...] = (
    Category("jeux-video/nintendo", "Jeux Nintendo (tous)", "Jeux Nintendo"),
    Category("jeux-video/nintendo/switch", "Jeux Switch", "Jeux Nintendo", "Switch"),
    Category("jeux-video/nintendo/3ds", "Jeux 3DS", "Jeux Nintendo", "3DS"),
    Category("jeux-video/nintendo/ds", "Jeux DS", "Jeux Nintendo", "DS"),
    Category("jeux-video/nintendo/wii-u", "Jeux Wii U", "Jeux Nintendo", "Wii U"),
    Category("jeux-video/nintendo/wii", "Jeux Wii", "Jeux Nintendo", "Wii"),
    Category("jeux-video/nintendo/gamecube", "Jeux GameCube", "Jeux Nintendo", "GameCube"),
)

_JEUX_MICROSOFT: tuple[Category, ...] = (
    Category("jeux-video/microsoft", "Jeux Microsoft (tous)", "Jeux Microsoft"),
    Category("jeux-video/microsoft/xbox-series", "Jeux Xbox Series", "Jeux Microsoft", "Xbox Series"),
    Category("jeux-video/microsoft/xbox-one", "Jeux Xbox One", "Jeux Microsoft", "Xbox One"),
    Category("jeux-video/microsoft/xbox-360", "Jeux Xbox 360", "Jeux Microsoft", "Xbox 360"),
)

# --- Consoles par plateforme -----------------------------------------------

_CONSOLES_SONY: tuple[Category, ...] = (
    Category("consoles/sony", "Consoles Sony (toutes)", "Consoles Sony"),
    Category("consoles/sony/ps5", "Consoles PS5", "Consoles Sony", "PS5"),
    Category("consoles/sony/ps4", "Consoles PS4", "Consoles Sony", "PS4"),
    Category("consoles/sony/ps3", "Consoles PS3", "Consoles Sony", "PS3"),
)

_CONSOLES_NINTENDO: tuple[Category, ...] = (
    Category("consoles/nintendo", "Consoles Nintendo (toutes)", "Consoles Nintendo"),
    Category("consoles/nintendo/switch", "Consoles Switch", "Consoles Nintendo", "Switch"),
    Category("consoles/nintendo/3ds", "Consoles 3DS", "Consoles Nintendo", "3DS"),
    Category("consoles/nintendo/wii-u", "Consoles Wii U", "Consoles Nintendo", "Wii U"),
    Category("consoles/nintendo/wii", "Consoles Wii", "Consoles Nintendo", "Wii"),
)

_CONSOLES_MICROSOFT: tuple[Category, ...] = (
    Category("consoles/microsoft", "Consoles Microsoft (toutes)", "Consoles Microsoft"),
    Category("consoles/microsoft/xbox-series", "Consoles Xbox Series", "Consoles Microsoft", "Xbox Series"),
    Category("consoles/microsoft/xbox-one", "Consoles Xbox One", "Consoles Microsoft", "Xbox One"),
)

# --- Agrégation ------------------------------------------------------------

CATEGORIES: tuple[Category, ...] = (
    _BROAD
    + _JEUX_SONY + _JEUX_NINTENDO + _JEUX_MICROSOFT
    + _CONSOLES_SONY + _CONSOLES_NINTENDO + _CONSOLES_MICROSOFT
)

CATEGORIES_BY_SLUG: dict[str, Category] = {c.slug: c for c in CATEGORIES}

# Liste groupée pour l'UI
GROUPS: dict[str, list[Category]] = {}
for _c in CATEGORIES:
    GROUPS.setdefault(_c.group, []).append(_c)


def get(slug: str) -> Category | None:
    return CATEGORIES_BY_SLUG.get(slug)
