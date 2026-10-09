"""The web_events.json contract the frontend builds from."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

import pytest

from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import CONFIRMED_TIME, FALLBACK_TIME, get_display_time
from boringhannover.exporters import export_web_json
from boringhannover.models import Event


if TYPE_CHECKING:
    from pathlib import Path


def _event(title: str, hour: int, minute: int = 0, **metadata: object) -> Event:
    return Event(
        title=title,
        date=datetime(2026, 7, 4, hour, minute, tzinfo=BERLIN_TZ),
        venue=str(metadata.pop("venue", "Venue")),
        url=f"https://example.com/{title.casefold().replace(' ', '-')}",
        category=str(metadata.pop("category", "radar")),  # type: ignore[arg-type]
        metadata=metadata,
    )


def _export(tmp_path: Path, movies: list[Event], concerts: list[Event]) -> dict:
    export_web_json(
        movies,
        concerts,
        tmp_path,
        27,
        2026,
        generated_at=datetime(2026, 7, 26, 16, 8, tzinfo=BERLIN_TZ),
    )
    return json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("confidence", "displayed"),
    [(CONFIRMED_TIME, "19:30"), (FALLBACK_TIME, None)],
)
def test_only_confirmed_times_are_displayed(
    confidence: str, displayed: str | None
) -> None:
    event = _event("Show", 19, 30, time="19:30", time_confidence=confidence)

    assert get_display_time(event) == displayed


def test_concerts_carry_null_fallback_times_and_canonical_genres(
    tmp_path: Path,
) -> None:
    data = _export(
        tmp_path,
        [],
        [
            _event(
                "Date Only",
                20,
                time="20:00",
                time_confidence=FALLBACK_TIME,
                genre="Mit Big Honey",
            ),
            _event(
                "Confirmed",
                19,
                30,
                time="19:30",
                time_confidence=CONFIRMED_TIME,
                genre="Garage Punk",
            ),
        ],
    )

    assert [
        (c["title"], c["time"], c["timeConfidence"], c["genre"])
        for c in data["concerts"]
    ] == [
        ("Confirmed", "19:30", CONFIRMED_TIME, "Punk / Hardcore"),
        ("Date Only", None, FALLBACK_TIME, None),
    ]


def test_movies_keep_canonical_venue_names(tmp_path: Path) -> None:
    data = _export(
        tmp_path,
        [
            _event("Astor Film", 18, venue="Astor Grand Cinema", category="movie"),
            _event(
                "Apollo Film", 22, 30, venue="Apollokino Hannover", category="movie"
            ),
        ],
        [],
    )

    assert [movie["venue"] for movie in data["movies"][0]["movies"]] == [
        "Astor Grand Cinema",
        "Apollokino Hannover",
    ]


def test_meta_has_a_machine_readable_timestamp_for_the_same_instant(
    tmp_path: Path,
) -> None:
    """The sitemap's <lastmod> comes from updatedAtISO: the display string
    parses to the year 2001."""
    meta = _export(tmp_path, [], [])["meta"]

    parsed = datetime.fromisoformat(meta["updatedAtISO"])
    assert parsed == datetime(2026, 7, 26, 16, 8, tzinfo=BERLIN_TZ)
    assert parsed.strftime("%a %d %b %H:%M") == meta["updatedAt"]
