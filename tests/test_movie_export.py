"""Tests for the movie-specific web export contract."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from boringhannover.constants import BERLIN_TZ
from boringhannover.exporters import export_web_json
from boringhannover.models import Event


def test_web_movie_export_preserves_canonical_venue_names(tmp_path: Path) -> None:
    movies = [
        Event(
            title="Astor Film",
            date=datetime(2026, 8, 28, 18, 0, tzinfo=BERLIN_TZ),
            venue="Astor Grand Cinema",
            url="https://hannover.premiumkino.de/film/astor-film",
            category="movie",
        ),
        Event(
            title="Apollo Film",
            date=datetime(2026, 8, 28, 22, 30, tzinfo=BERLIN_TZ),
            venue="Apollokino Hannover",
            url="https://www.apollokino.de/film/apollo-film",
            category="movie",
        ),
    ]

    export_web_json(movies, [], tmp_path, 35, 2026)

    data = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))
    exported_movies = data["movies"][0]["movies"]

    assert [movie["venue"] for movie in exported_movies] == [
        "Astor Grand Cinema",
        "Apollokino Hannover",
    ]


def test_web_movie_export_carries_an_unambiguous_iso_date_per_day(
    tmp_path: Path,
) -> None:
    """The "%d.%m" display date cannot be resolved to a year by consumers."""
    movies = [
        Event(
            title="Silvester Screening",
            date=datetime(2026, 12, 31, 21, 0, tzinfo=BERLIN_TZ),
            venue="Astor Grand Cinema",
            url="https://hannover.premiumkino.de/film/silvester",
            category="movie",
        ),
        Event(
            title="Neujahr Screening",
            date=datetime(2027, 1, 1, 15, 0, tzinfo=BERLIN_TZ),
            venue="Astor Grand Cinema",
            url="https://hannover.premiumkino.de/film/neujahr",
            category="movie",
        ),
    ]

    export_web_json(movies, [], tmp_path, 53, 2026)

    data = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))

    assert [day["dateISO"] for day in data["movies"]] == ["2026-12-31", "2027-01-01"]
