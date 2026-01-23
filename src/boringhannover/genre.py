"""Genre normalization for concert events.

Provides a canonical genre taxonomy and normalization function
for consistent genre display across all concert sources.
"""

from __future__ import annotations

from typing import Final


__all__ = [
    "CANONICAL_GENRES",
    "GENRE_SYNONYMS",
    "normalize_genre",
]


# 9 canonical genres for the Hannover concert scene
CANONICAL_GENRES: Final[tuple[str, ...]] = (
    "Rock",
    "Punk / Hardcore",
    "Metal",
    "Pop",
    "Hip-Hop",
    "Electronic",
    "Jazz / Blues",
    "Klassik",
    "Folk / World",
)


# Mapping from raw genre strings to canonical genres (case-insensitive)
GENRE_SYNONYMS: Final[dict[str, str]] = {
    # Rock variants
    "rock": "Rock",
    "indie": "Rock",
    "alternative": "Rock",
    "alt-rock": "Rock",
    "grunge": "Rock",
    "post-rock": "Rock",
    "prog rock": "Rock",
    "deutschrock": "Rock",
    "krautrock": "Rock",
    "britpop": "Rock",
    # Punk variants
    "punk": "Punk / Hardcore",
    "punk rock": "Punk / Hardcore",
    "hardcore": "Punk / Hardcore",
    "hardcore punk": "Punk / Hardcore",
    "post-punk": "Punk / Hardcore",
    "postpunk": "Punk / Hardcore",
    "oi": "Punk / Hardcore",
    "crust": "Punk / Hardcore",
    # Metal variants
    "metal": "Metal",
    "heavy metal": "Metal",
    "death metal": "Metal",
    "black metal": "Metal",
    "thrash": "Metal",
    "neue deutsche härte": "Metal",
    # Pop variants
    "pop": "Pop",
    "synth-pop": "Pop",
    "dance-pop": "Pop",
    "neue deutsche welle": "Pop",
    "ndw": "Pop",
    # Hip-Hop variants
    "hip hop": "Hip-Hop",
    "hip-hop": "Hip-Hop",
    "hiphop": "Hip-Hop",
    "rap": "Hip-Hop",
    "trap": "Hip-Hop",
    # Electronic variants
    "electronic": "Electronic",
    "techno": "Electronic",
    "house": "Electronic",
    "trance": "Electronic",
    "drum and bass": "Electronic",
    "dnb": "Electronic",
    "dubstep": "Electronic",
    "ambient": "Electronic",
    "edm": "Electronic",
    "elektronisch": "Electronic",
    "elektronische musik": "Electronic",
    # Jazz / Blues variants
    "jazz": "Jazz / Blues",
    "blues": "Jazz / Blues",
    "soul": "Jazz / Blues",
    "r&b": "Jazz / Blues",
    "rnb": "Jazz / Blues",
    "funk": "Jazz / Blues",
    "disco": "Jazz / Blues",
    # Klassik variants
    "klassik": "Klassik",
    "classical": "Klassik",
    "klassische musik": "Klassik",
    "baroque": "Klassik",
    "orchestra": "Klassik",
    "orchester": "Klassik",
    # Folk / World variants
    "folk": "Folk / World",
    "singer-songwriter": "Folk / World",
    "liedermacher": "Folk / World",
    "acoustic": "Folk / World",
    "country": "Folk / World",
    "world": "Folk / World",
    "reggae": "Folk / World",
    "ska": "Folk / World",
    "dub": "Folk / World",
    "schlager": "Folk / World",
    "volksmusik": "Folk / World",
    "volkstümlich": "Folk / World",
}


def normalize_genre(raw: str) -> str | None:
    """Normalize a raw genre string to a canonical genre.

    Args:
        raw: Raw genre string from source (e.g., "Punk Rock", "elektronisch").

    Returns:
        Canonical genre string if found in synonyms, None otherwise.

    Examples:
        >>> normalize_genre("punk rock")
        'Punk / Hardcore'
        >>> normalize_genre("Elektronisch")
        'Electronic'
        >>> normalize_genre("Unknown Genre")
        None
    """
    if not raw:
        return None

    key = raw.lower().strip()
    return GENRE_SYNONYMS.get(key)
