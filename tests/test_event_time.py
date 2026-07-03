"""Tests for event time confidence handling."""

from __future__ import annotations

import json
from datetime import datetime

from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import (
    CONFIRMED_TIME,
    FALLBACK_TIME,
    get_display_time,
)
from boringhannover.exporters import export_web_json
from boringhannover.formatting import format_radar_section
from boringhannover.models import Event
from boringhannover.sources.concerts.faust import FaustSource
from boringhannover.sources.concerts.glocke import GlockseeSource
from boringhannover.sources.concerts.punkrock_konzerte import PunkrockKonzerteSource


def test_confirmed_time_is_displayed() -> None:
    event = Event(
        title="Confirmed",
        date=datetime(2026, 7, 4, 19, 30, tzinfo=BERLIN_TZ),
        venue="Venue",
        url="https://example.com",
        category="radar",
        metadata={"time": "19:30", "time_confidence": CONFIRMED_TIME},
    )

    assert get_display_time(event) == "19:30"


def test_fallback_time_is_hidden_from_display() -> None:
    event = Event(
        title="Date Only",
        date=datetime(2026, 7, 4, 20, 0, tzinfo=BERLIN_TZ),
        venue="Venue",
        url="https://example.com",
        category="radar",
        metadata={"time": "20:00", "time_confidence": FALLBACK_TIME},
    )

    assert get_display_time(event) is None


def test_radar_format_omits_fallback_time() -> None:
    event = Event(
        title="Date Only",
        date=datetime(2026, 7, 4, 20, 0, tzinfo=BERLIN_TZ),
        venue="Venue",
        url="https://example.com",
        category="radar",
        metadata={"time": "20:00", "time_confidence": FALLBACK_TIME},
    )

    result = format_radar_section([event])

    assert "Date Only" in result
    assert "20:00" not in result
    assert "| @" not in result
    assert "Sa, 4. Jul @ Venue" in result


def test_web_json_uses_null_for_fallback_time(tmp_path) -> None:
    fallback = Event(
        title="Date Only",
        date=datetime(2026, 7, 4, 20, 0, tzinfo=BERLIN_TZ),
        venue="Venue",
        url="https://example.com",
        category="radar",
        metadata={"time": "20:00", "time_confidence": FALLBACK_TIME},
    )
    confirmed = Event(
        title="Confirmed",
        date=datetime(2026, 7, 4, 19, 30, tzinfo=BERLIN_TZ),
        venue="Venue",
        url="https://example.com",
        category="radar",
        metadata={"time": "19:30", "time_confidence": CONFIRMED_TIME},
    )

    export_web_json([], [fallback, confirmed], tmp_path, 27, 2026)
    data = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))

    assert data["concerts"][0]["title"] == "Confirmed"
    assert data["concerts"][0]["time"] == "19:30"
    assert data["concerts"][0]["timeConfidence"] == CONFIRMED_TIME
    assert data["concerts"][1]["title"] == "Date Only"
    assert data["concerts"][1]["time"] is None
    assert data["concerts"][1]["timeConfidence"] == FALLBACK_TIME


def test_faust_parses_hour_only_beginn_as_confirmed_time() -> None:
    source = FaustSource()

    title, time_str, time_confidence, location, price = source._parse_event_content(
        [
            "So, 05.07.26",
            "Swinging Gretchen",
            "Biergarten Gretchen",
            "Eintritt: frei",
            "Einlass / Beginn: 14 Uhr",
        ]
    )

    assert title == "Swinging Gretchen"
    assert time_str == "14:00"
    assert time_confidence == CONFIRMED_TIME
    assert location == "Biergarten Gretchen"
    assert price == "Eintritt: frei"


def test_faust_parses_split_beginn_label_and_hour() -> None:
    source = FaustSource()

    title, time_str, time_confidence, _location, _price = source._parse_event_content(
        [
            "Fr, 17.07.26",
            "Die 90er-Party",
            "Einlass / Beginn:",
            "23 Uhr",
        ]
    )

    assert title == "Die 90er-Party"
    assert time_str == "23:00"
    assert time_confidence == CONFIRMED_TIME


def test_glocksee_parses_beginn_from_info_list() -> None:
    source = GlockseeSource()

    result = source._extract_confirmed_time(
        {
            "info_list": [
                {"info": "Einlass 20.00 Uhr"},
                {"info": "Beginn 21.15 Uhr"},
                {"info": "Eintritt frei"},
            ]
        }
    )

    assert result == (21, 15)


def test_punkrock_parses_kulturpalast_structured_start_date() -> None:
    source = PunkrockKonzerteSource()

    result = source._parse_kulturpalast_datetime(
        """
        <script type="application/ld+json">
        [{"@type":"Event","startDate":"2026-07-07T20:00:00+02:00"}]
        </script>
        """
    )

    assert result is not None
    assert result.hour == 20
    assert result.minute == 0
    assert result.tzinfo is not None
