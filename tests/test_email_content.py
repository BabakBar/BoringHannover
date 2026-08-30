"""The edition content model is derived only from the canonical web artifact."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from boringhannover.newsletter.content import build_edition_content


def _artifact(**overrides: Any) -> dict[str, Any]:
    """A minimal but realistic web_events.json payload."""
    artifact: dict[str, Any] = {
        "meta": {
            "week": 35,
            "year": 2026,
            "updatedAt": "Thu 27 Aug 00:12",
            "updatedAtISO": "2026-08-27T00:12:53.241038+02:00",
        },
        "movies": [
            {
                "day": "THU",
                "date": "27.08",
                "dateISO": "2026-08-27",
                "movies": [
                    {
                        "title": "Die Odyssee",
                        "time": "20:15",
                        "venue": "Astor Grand Cinema",
                        "duration": "2h52m",
                        "language": "EN",
                        "subtitles": None,
                        "rating": "FSK12",
                        "url": "https://hannover.premiumkino.de/film/die-odyssee",
                    }
                ],
            },
            {
                "day": "SUN",
                "date": "06.09",
                "dateISO": "2026-09-06",
                "movies": [
                    {
                        "title": "Too Late",
                        "time": "18:00",
                        "venue": "Astor Grand Cinema",
                        "url": "https://hannover.premiumkino.de/film/too-late",
                    }
                ],
            },
        ],
        "concerts": [
            {
                "title": "Some Band",
                "date": "29 Aug",
                "dateISO": "2026-08-29",
                "day": "Sa",
                "time": "20:00",
                "timeConfidence": "confirmed",
                "venue": "Capitol Hannover",
                "url": "https://www.capitol-hannover.de/events/some-band",
                "radarCategory": "Live Music",
                "status": "available",
            },
            {
                "title": "Way Later Band",
                "date": "20 Sep",
                "dateISO": "2026-09-20",
                "day": "So",
                "time": "19:00",
                "venue": "Pavillon",
                "url": "https://www.pavillon-hannover.de/way-later",
                "radarCategory": "Live Music",
                "status": "available",
            },
        ],
        "occasions": [
            {
                "id": "hannover-festivals:hola-utopia",
                "slug": "hola-utopia",
                "name": "Hola Utopia",
                "kind": "festival",
                "startDate": "2026-08-24",
                "endDate": "2026-08-30",
                "location": "Berufsbildende Schule 6",
                "description": "Street art week.",
                "sourceUrl": "https://www.hannover.de/hola-utopia",
                "status": "happening_now",
                "programmeCount": 4,
                "programmePath": "occasions/hola-utopia.json",
                "preview": [],
            },
            {
                "id": "hannover-festivals:next-month",
                "slug": "next-month",
                "name": "Next Month Fest",
                "kind": "festival",
                "startDate": "2026-10-01",
                "endDate": "2026-10-05",
                "location": "Somewhere",
                "description": "Later.",
                "sourceUrl": "https://www.hannover.de/next-month",
                "status": "upcoming",
                "programmeCount": 2,
                "programmePath": "occasions/next-month.json",
                "preview": [],
            },
        ],
    }
    artifact.update(overrides)
    return artifact


def test_window_starts_on_the_artifact_generation_day() -> None:
    content = build_edition_content(_artifact())

    assert content.window_start == date(2026, 8, 27)
    assert content.window_end == date(2026, 9, 2)


def test_edition_key_comes_from_the_window_start() -> None:
    assert build_edition_content(_artifact()).key == "hannover:2026-W35:en"


def test_only_events_inside_the_window_are_included() -> None:
    content = build_edition_content(_artifact())
    titles = {item.title for section in content.sections for item in section.items}

    assert titles == {"Die Odyssee", "Some Band", "Hola Utopia"}


def test_sections_are_ordered_and_empty_sections_are_dropped() -> None:
    artifact = _artifact()
    artifact["movies"] = []

    content = build_edition_content(artifact)

    assert [section.key for section in content.sections] == ["occasions", "radar"]


def test_items_within_a_section_are_ordered_by_date_then_time() -> None:
    artifact = _artifact()
    artifact["concerts"] = [
        {
            "title": "Later Same Day",
            "dateISO": "2026-08-29",
            "time": "22:00",
            "venue": "Faust",
            "url": "https://kulturzentrum-faust.de/later",
        },
        {
            "title": "Earlier Same Day",
            "dateISO": "2026-08-29",
            "time": "18:00",
            "venue": "Faust",
            "url": "https://kulturzentrum-faust.de/earlier",
        },
        {
            "title": "Day Before",
            "dateISO": "2026-08-28",
            "time": "23:00",
            "venue": "Faust",
            "url": "https://kulturzentrum-faust.de/before",
        },
    ]

    content = build_edition_content(artifact)
    radar = next(s for s in content.sections if s.key == "radar")

    assert [item.title for item in radar.items] == [
        "Day Before",
        "Earlier Same Day",
        "Later Same Day",
    ]


def test_movie_items_carry_language_and_runtime_as_a_note() -> None:
    content = build_edition_content(_artifact())
    movies = next(s for s in content.sections if s.key == "movies")

    assert movies.items[0].note == "EN · 2h52m · FSK12"


def test_occasion_items_span_their_whole_run() -> None:
    content = build_edition_content(_artifact())
    occasions = next(s for s in content.sections if s.key == "occasions")

    assert occasions.items[0].date_display == "Mon 24 Aug - Sun 30 Aug"
    assert occasions.items[0].note == "Berufsbildende Schule 6 · 4 programme items"


def test_revision_ignores_the_generation_timestamp() -> None:
    first = build_edition_content(_artifact())
    later = _artifact()
    later["meta"]["updatedAt"] = "Thu 27 Aug 23:59"
    later["meta"]["updatedAtISO"] = "2026-08-27T23:59:00+02:00"

    assert build_edition_content(later).revision == first.revision


def test_revision_changes_when_an_event_changes() -> None:
    first = build_edition_content(_artifact())
    changed = _artifact()
    changed["concerts"][0]["time"] = "21:00"

    assert build_edition_content(changed).revision != first.revision


def test_content_is_empty_when_nothing_falls_in_the_window() -> None:
    artifact = _artifact()
    artifact["movies"] = []
    artifact["concerts"] = []
    artifact["occasions"] = []

    content = build_edition_content(artifact)

    assert content.sections == ()
    assert content.is_empty


def test_a_missing_generation_timestamp_fails_closed() -> None:
    artifact = _artifact()
    del artifact["meta"]["updatedAtISO"]

    with pytest.raises(ValueError, match="updatedAtISO"):
        build_edition_content(artifact)


def test_an_unparseable_generation_timestamp_fails_closed() -> None:
    artifact = _artifact()
    artifact["meta"]["updatedAtISO"] = "letzten Donnerstag"

    with pytest.raises(ValueError, match="updatedAtISO"):
        build_edition_content(artifact)


def test_events_without_a_usable_iso_date_are_skipped_not_guessed() -> None:
    artifact = _artifact()
    artifact["concerts"].append(
        {
            "title": "No Date Band",
            "dateISO": None,
            "time": "20:00",
            "venue": "Unknown",
            "url": "https://example.com/no-date",
        }
    )

    content = build_edition_content(artifact)
    titles = {item.title for section in content.sections for item in section.items}

    assert "No Date Band" not in titles
