"""Broad, user-facing categories for the mixed Events Radar."""

from __future__ import annotations

from typing import Final, Literal


__all__ = [
    "RADAR_CATEGORIES",
    "RadarCategory",
    "classify_radar_category",
]

RadarCategory = Literal[
    "Live Music",
    "Party",
    "Culture & Community",
    "Workshop",
    "Sport",
    "Market",
    "Film",
    "Food & Drink",
]

RADAR_CATEGORIES: Final[tuple[RadarCategory, ...]] = (
    "Live Music",
    "Party",
    "Culture & Community",
    "Workshop",
    "Sport",
    "Market",
    "Film",
    "Food & Drink",
)

_TEXT_RULES: Final[tuple[tuple[RadarCategory, tuple[str, ...]], ...]] = (
    (
        "Sport",
        (
            "finals 2026 hannover",
            "kickbox",
            "krökel",
            "sport",
            "training",
            "turnier",
            "yoga",
        ),
    ),
    (
        "Film",
        (
            "film screening",
            "kino",
            "platzkino",
        ),
    ),
    (
        "Market",
        (
            "flohmarkt",
            "stecklingsverkauf",
        ),
    ),
    (
        "Workshop",
        (
            "bastel",
            "sommercamp",
            "schreibtreff",
            "wildes schreiben",
            "workshop",
        ),
    ),
    (
        "Food & Drink",
        (
            "bierausschank",
            "cafe",
            "café",
            "ka'fe",
        ),
    ),
    (
        "Culture & Community",
        (
            "community",
            "connect & growth",
            "mitmachen",
            "offener treff",
            "plenum",
            "rundgang",
        ),
    ),
)

_LIVE_MUSIC_MARKERS: Final[tuple[str, ...]] = (
    "jazz session",
    "konzert",
    "live music",
    "live musik",
    "music session",
)

_PARTY_MARKERS: Final[tuple[str, ...]] = (
    "club night",
    "disco",
    "party",
    "social dance",
)


def classify_radar_category(
    title: str,
    *,
    description: str = "",
    event_type: str = "",
    genre: str = "",
) -> RadarCategory:
    """Classify an event using explicit types and conservative text markers."""
    searchable = f"{title} {description}".casefold().replace(
        "\N{RIGHT SINGLE QUOTATION MARK}",
        "'",
    )

    for category, markers in _TEXT_RULES:
        if any(marker in searchable for marker in markers):
            return category

    normalized_type = event_type.casefold().strip()
    if normalized_type == "party":
        return "Party"
    if normalized_type == "sport":
        return "Sport"

    if any(marker in searchable for marker in _PARTY_MARKERS):
        return "Party"

    if (
        normalized_type in {"concert", "konzert", "live_music"}
        or genre
        or any(marker in searchable for marker in _LIVE_MUSIC_MARKERS)
    ):
        return "Live Music"

    return "Culture & Community"
