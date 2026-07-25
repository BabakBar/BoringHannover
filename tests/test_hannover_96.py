"""Tests for the official Hannover 96 home-match calendar source."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import CONFIRMED_TIME
from boringhannover.sources import get_source
from boringhannover.sources.sports.hannover_96 import Hannover96Source


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_calendar_keeps_only_future_public_home_matches_with_kickoffs() -> None:
    source = Hannover96Source()
    calendar = (FIXTURES / "hannover_96_matches.ics").read_text(encoding="utf-8")

    events = source._parse_calendar(
        calendar,
        now=datetime(2026, 7, 26, 12, 0, tzinfo=BERLIN_TZ),
    )

    assert [event.title for event in events] == [
        "Hannover 96 vs. VfL Wolfsburg",
        "Hannover 96 vs. Phönix Lübeck",
    ]

    league_match = events[0]
    assert league_match.date == datetime(2026, 8, 16, 13, 30, tzinfo=BERLIN_TZ)
    assert league_match.venue == "Heinz von Heiden Arena"
    assert league_match.category == "radar"
    assert league_match.url == source.SCHEDULE_URL
    assert league_match.metadata == {
        "time": "13:30",
        "time_confidence": CONFIRMED_TIME,
        "event_type": "sport",
        "competition": "2. Bundesliga",
        "opponent": "VfL Wolfsburg",
        "address": source.ARENA_ADDRESS,
    }

    friendly = events[1]
    assert friendly.date == datetime(2026, 8, 18, 18, 0, tzinfo=BERLIN_TZ)
    assert friendly.venue == "Eilenriedestadion"
    assert friendly.metadata["competition"] == "Testspiel"
    assert "address" not in friendly.metadata


def test_unknown_opponent_abbreviation_is_kept_readable() -> None:
    source = Hannover96Source()

    assert source._expand_opponent("XYZ") == "XYZ"


def test_source_is_registered_as_sport() -> None:
    source_class = get_source("hannover_96")

    assert source_class is Hannover96Source
    assert source_class.source_type == "sport"
