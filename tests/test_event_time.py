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
