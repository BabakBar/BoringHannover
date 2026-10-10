"""Reader-facing text: genres, Radar categories and truncation."""

from __future__ import annotations

import pytest

from boringhannover.genre import normalize_genre
from boringhannover.radar_categories import classify_radar_category
from boringhannover.sanitize import sanitize_text, truncate_text


# Real LUX description that used to publish as "...das ebenfalls de".
LUX_TEXT = (
    "Sean Koch kehrt mit einem brandneuen Album und einer noch nie dagewesenen "
    "Show nach Europa zurück. Die „Time Will Tell“-Tour feiert die "
    "Veröffentlichung von Seans drittem Studioalbum, das ebenfalls denselben "
    "Namen trägt."
)


@pytest.mark.parametrize(
    ("raw", "genre"),
    [
        *[
            (raw, "Punk / Hardcore")
            for raw in (
                "punk",
                "PUNK",
                "punk rock",
                "hardcore",
                "hardcore punk",
                "post-punk",
                "postpunk",
                "  punk  ",
            )
        ],
        *[
            (raw, "Electronic")
            for raw in (
                "electronic",
                "techno",
                "house",
                "trance",
                "elektronisch",
                "edm",
            )
        ],
        *[
            (raw, "Rock")
            for raw in (
                "rock",
                "indie",
                "alternative",
                "krautrock",
                "britpop",
                "\trock\n",
            )
        ],
        *[
            (raw, "Metal")
            for raw in ("METAL", "heavy metal", "death metal", "neue deutsche härte")
        ],
        *[(raw, "Hip-Hop") for raw in ("hip hop", "hip-hop", "hiphop", "rap")],
        *[(raw, "Jazz / Blues") for raw in ("JAZZ", "blues", "soul", "funk")],
        *[(raw, "Klassik") for raw in ("klassik", "classical", "orchestra")],
        *[
            (raw, "Folk / World")
            for raw in ("folk", "reggae", "ska", "schlager", "liedermacher")
        ],
        *[(raw, "Pop") for raw in ("pop", "synth-pop", "ndw")],
        # A known genre word inside a descriptive tagline.
        ("Garage Punk", "Punk / Hardcore"),
        ("Feine elektronische Musik", "Electronic"),
        ("Indie Rock aus Hannover", "Rock"),
        # Unknown genres and artist billing are never exposed as a genre.
        *[
            (raw, None)
            for raw in ("zydeco", "polka", "unknown genre", "", "   ", "Mit Big Honey")
        ],
    ],
)
def test_normalize_genre(raw: str, genre: str | None) -> None:
    assert normalize_genre(raw) == genre


@pytest.mark.parametrize(
    ("title", "description", "event_type", "category"),
    [
        ("Hatebreed", "", "concert", "Live Music"),
        ("Disco Deluxe", "", "party", "Party"),
        ("Home match", "", "sport", "Sport"),
        # Source text only counts with a high-confidence marker.
        ("PLATZkino \N{EN DASH} heute mit Parasite", "", None, "Film"),
        ("Kickboxen von Lumino", "", None, "Sport"),
        ("Sonntagsflohmarkt", "", None, "Market"),
        ("Wildes Schreiben mit Heike", "", None, "Workshop"),
        ("[Ka\N{RIGHT SINGLE QUOTATION MARK}fe:] Container", "", None, "Food & Drink"),
        ("öffentliches OSCO Plenum", "", None, "Culture & Community"),
        ("Konzert ZeWitches", "", None, "Live Music"),
        # Specific markers beat a generic source event type.
        (
            "Blaue Zone Sommercamp",
            "Zehn Sommertage voller Workshops, Musik und Essen.",
            "event",
            "Workshop",
        ),
        ("Swing am PLATZ", "Social dance party with DJ.", "event", "Party"),
        ("FINALS 2026 HANNOVER", "", "concert", "Sport"),
        # Unknown general events stay honestly broad.
        ("A new local gathering", "", None, "Culture & Community"),
    ],
)
def test_radar_category(
    title: str, description: str, event_type: str | None, category: str
) -> None:
    kwargs = {"event_type": event_type} if event_type else {}
    if description:
        kwargs["description"] = description

    assert classify_radar_category(title, **kwargs) == category


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [
        ("Offenes Krökeln", 200, "Offenes Krökeln"),
        ("a" * 20, 20, "a" * 20),
        # Cut on a word boundary, dropping trailing punctuation.
        ("Workshops, Vorträge, Essen, Party", 20, "Workshops, Vorträge…"),
        # No usable space: hard cut.
        ("x" * 300, 200, "x" * 199 + "…"),
    ],
)
def test_truncate_text(text: str, limit: int, expected: str) -> None:
    assert truncate_text(text, limit) == expected


def test_long_descriptions_end_on_a_whole_word() -> None:
    for limit in (10, 50, 157, 200):
        assert len(truncate_text(LUX_TEXT, limit)) <= limit

    truncated = truncate_text(LUX_TEXT, 200)
    assert truncated.endswith("ebenfalls…")
    assert LUX_TEXT.startswith(truncated.removesuffix("…"))

    sanitized = sanitize_text(f"<p>{LUX_TEXT}</p>", 200)
    assert sanitized.endswith("ebenfalls…")
    assert "..." not in sanitized


@pytest.mark.parametrize(
    ("raw", "limit", "expected"),
    [
        # hannover.de hyphenates titles with U+00AD, literally or encoded (#60).
        ("Fähr\N{SOFT HYPHEN}manns\N{SOFT HYPHEN}fest 2026", 500, "Fährmannsfest 2026"),
        ("Fähr&shy;manns&shy;fest 2026", 500, "Fährmannsfest 2026"),
        ("Fähr&#173;manns&#xAD;fest 2026", 500, "Fährmannsfest 2026"),
        (
            "<span>Fähr&#xad;manns</span>\N{SOFT HYPHEN}fest 2026",
            500,
            "Fährmannsfest 2026",
        ),
        # Soft hyphens are dropped before the limit applies.
        ("Ent\N{SOFT HYPHEN}decker\N{SOFT HYPHEN}tag", 12, "Entdeckertag"),
        # Ordinary Unicode is kept.
        (
            "Kunst & Kürbis \N{EN DASH} Café „Glocksee“",
            500,
            "Kunst & Kürbis \N{EN DASH} Café „Glocksee“",
        ),
    ],
)
def test_sanitize_text_removes_soft_hyphens(
    raw: str, limit: int, expected: str
) -> None:
    assert sanitize_text(raw, limit) == expected
