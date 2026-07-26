"""Tests for the official Platzprojekt events API source."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import CONFIRMED_TIME, FALLBACK_TIME
from boringhannover.sources import get_source
from boringhannover.sources.concerts.platzprojekt import PlatzprojektSource


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_payload_keeps_public_events_and_cleans_api_fields() -> None:
    source = PlatzprojektSource()
    payload = json.loads(
        (FIXTURES / "platzprojekt_events.json").read_text(encoding="utf-8")
    )

    events = source._parse_payload(
        payload,
        now=datetime(2026, 7, 26, 12, 0, tzinfo=BERLIN_TZ),
    )

    assert [event.title for event in events] == [
        "PLATZkino – heute mit „Parasite“",  # noqa: RUF001
        "Blaue Zone Sommercamp",
        "Offenes Krökeln",
    ]

    timed = events[0]
    assert timed.date == datetime(2026, 7, 28, 20, 0, tzinfo=BERLIN_TZ)
    assert timed.venue == "OSCO – OpenSpace"  # noqa: RUF001
    assert timed.category == "radar"
    assert timed.metadata == {
        "time": "20:00",
        "time_confidence": CONFIRMED_TIME,
        "end_time": "23:00",
        "event_type": "event",
        "subtitle": "Jeden vierten Dienstag findet das PLATZkino statt.",
        "description": "Jeden vierten Dienstag findet das PLATZkino statt.",
        "image_url": (
            "https://platzprojekt.de/wp-content/uploads/2026/07/platzkino.jpg"
        ),
        "address": "Fössestr. 103, 30453 Hannover",
        "price": "5 €",
        "source_name": "PLATZprojekt",
    }

    all_day = events[1]
    assert all_day.date == datetime(2026, 7, 30, 12, 0, tzinfo=BERLIN_TZ)
    assert all_day.metadata["time_confidence"] == FALLBACK_TIME
    assert all_day.metadata["end_time"] == ""

    default_venue = events[2]
    assert default_venue.venue == source.source_name
    assert default_venue.metadata["address"] == source.ADDRESS


def test_parse_payload_rejects_malformed_top_level_data() -> None:
    source = PlatzprojektSource()
    now = datetime(2026, 7, 26, 12, 0, tzinfo=BERLIN_TZ)

    assert source._parse_payload([], now=now) == []
    assert source._parse_payload({"events": "invalid"}, now=now) == []


def test_source_is_registered_as_event_source() -> None:
    source_class = get_source("platzprojekt")

    assert source_class is PlatzprojektSource
    assert source_class.source_type == "event"
