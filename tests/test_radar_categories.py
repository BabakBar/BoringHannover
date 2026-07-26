"""Tests for the user-facing Radar category taxonomy."""

from boringhannover.radar_categories import classify_radar_category


def test_explicit_event_types_map_to_broad_radar_categories() -> None:
    assert classify_radar_category("Hatebreed", event_type="concert") == "Live Music"
    assert classify_radar_category("Disco Deluxe", event_type="party") == "Party"
    assert classify_radar_category("Home match", event_type="sport") == "Sport"


def test_source_text_only_uses_high_confidence_category_markers() -> None:
    assert (
        classify_radar_category("PLATZkino \N{EN DASH} heute mit Parasite") == "Film"
    )
    assert classify_radar_category("Kickboxen von Lumino") == "Sport"
    assert classify_radar_category("Sonntagsflohmarkt") == "Market"
    assert classify_radar_category("Wildes Schreiben mit Heike") == "Workshop"
    assert (
        classify_radar_category("[Ka\N{RIGHT SINGLE QUOTATION MARK}fe:] Container")
        == "Food & Drink"
    )
    assert classify_radar_category("öffentliches OSCO Plenum") == (
        "Culture & Community"
    )
    assert classify_radar_category("Konzert ZeWitches") == "Live Music"


def test_specific_markers_override_a_generic_source_event_type() -> None:
    assert (
        classify_radar_category(
            "Blaue Zone Sommercamp",
            description="Zehn Sommertage voller Workshops, Musik und Essen.",
            event_type="event",
        )
        == "Workshop"
    )
    assert (
        classify_radar_category(
            "Swing am PLATZ",
            description="Social dance party with DJ.",
            event_type="event",
        )
        == "Party"
    )
    assert classify_radar_category(
        "FINALS 2026 HANNOVER",
        event_type="concert",
    ) == "Sport"


def test_unknown_general_events_remain_honestly_broad() -> None:
    assert classify_radar_category("A new local gathering") == (
        "Culture & Community"
    )
