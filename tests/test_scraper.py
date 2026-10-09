"""Tests for BoringHannover scraper functionality.

Tests cover the core modules:
- models: Event dataclass and methods
- scrapers: Event fetching and parsing
- main: CLI and workflow orchestration
"""

from __future__ import annotations

from datetime import datetime, timedelta

from boringhannover.aggregator import fetch_all_events
from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import FALLBACK_TIME
from boringhannover.formatting import format_radar_section
from boringhannover.models import Event
from boringhannover.notifier import format_message
from boringhannover.sources.base import BaseSource


# =============================================================================
# Event Model Tests
# =============================================================================


class TestEventModel:
    """Tests for the Event dataclass."""

    def test_event_format_date_short(self) -> None:
        """Test short date formatting."""
        event = Event(
            title="Test",
            date=datetime(2024, 11, 24, 19, 30, tzinfo=BERLIN_TZ),
            venue="Venue",
            url="https://example.com",
            category="movie",
        )
        # Format: "Sun 24.11."  # noqa: ERA001
        result = event.format_date_short()
        assert "24.11." in result

    def test_event_format_time(self) -> None:
        """Test time formatting."""
        event = Event(
            title="Test",
            date=datetime(2024, 11, 24, 19, 30, tzinfo=BERLIN_TZ),
            venue="Venue",
            url="https://example.com",
            category="movie",
        )
        result = event.format_time()
        assert "19:30" in result

    def test_event_is_this_week(self) -> None:
        """Test this week detection."""
        today = datetime.now(BERLIN_TZ)
        tomorrow = today + timedelta(days=1)
        next_month = today + timedelta(days=30)

        event_this_week = Event(
            title="This Week",
            date=tomorrow,
            venue="Venue",
            url="https://example.com",
            category="movie",
        )
        event_next_month = Event(
            title="Next Month",
            date=next_month,
            venue="Venue",
            url="https://example.com",
            category="movie",
        )

        assert event_this_week.is_this_week() is True
        assert event_next_month.is_this_week() is False

    def test_event_normalizes_naive_datetime_to_berlin_tz(self) -> None:
        """Naive datetimes are treated as Europe/Berlin."""
        naive = datetime(2025, 12, 12, 19, 30)  # noqa: DTZ001
        event = Event(
            title="Naive Date",
            date=naive,
            venue="Venue",
            url="https://example.com",
            category="movie",
        )
        assert event.date.tzinfo is BERLIN_TZ
        assert (event.date.hour, event.date.minute) == (19, 30)


class TestFetchAllEvents:
    """Tests for the event aggregation function."""

    def test_handles_naive_datetimes_from_sources(self) -> None:
        """Sources may emit naive datetimes; aggregation should not crash."""
        today = datetime.now(BERLIN_TZ)

        class StaticSource(BaseSource):
            source_name = "Static"
            source_type = "cinema"

            def fetch(self) -> list[Event]:
                return [
                    Event(
                        title="Movie",
                        date=(today + timedelta(days=1)).replace(tzinfo=None),
                        venue="Venue",
                        url="https://example.com",
                        category="movie",
                    ),
                    Event(
                        title="Concert",
                        date=(today + timedelta(days=8)).replace(tzinfo=None),
                        venue="Venue",
                        url="https://example.com",
                        category="radar",
                    ),
                ]

        result = fetch_all_events(sources={"static": StaticSource})

        assert [e.title for e in result["movies_this_week"]] == ["Movie"]
        assert [e.title for e in result["big_events_radar"]] == ["Concert"]


# =============================================================================
# Notifier Tests
# =============================================================================


class TestFormatMessage:
    """Tests for message formatting."""

    def test_format_message_includes_sections(self) -> None:
        """Test that formatted message includes all sections."""
        test_data = {
            "movies_this_week": [],
            "big_events_radar": [],
        }
        result = format_message(test_data)

        assert "Movies" in result
        assert "Radar" in result

    def test_format_message_with_movies(self) -> None:
        """Test formatting with movie events."""
        movie = Event(
            title="Inception",
            date=datetime(2024, 11, 24, 19, 30, tzinfo=BERLIN_TZ),
            venue="Astor Grand Cinema",
            url="https://example.com",
            category="movie",
            metadata={"duration": 148, "year": 2010, "language": "Sprache: Englisch"},
        )
        test_data = {
            "movies_this_week": [movie],
            "big_events_radar": [],
        }
        result = format_message(test_data)

        assert "Inception" in result
        assert "2010" in result
        assert "19:30" in result

    def test_format_message_with_concerts(self) -> None:
        """Test formatting with concert events."""
        concert = Event(
            title="Rock Concert",
            date=datetime(2024, 12, 15, 20, 0, tzinfo=BERLIN_TZ),
            venue="ZAG Arena",
            url="https://example.com",
            category="radar",
            metadata={"time": "20:00"},
        )
        test_data = {
            "movies_this_week": [],
            "big_events_radar": [concert],
        }
        result = format_message(test_data)

        assert "Rock Concert" in result
        assert "ZAG Arena" in result
        assert "20:00" in result

    def test_format_message_handles_empty_data(self) -> None:
        """Test that empty data is handled gracefully."""
        test_data = {
            "movies_this_week": [],
            "big_events_radar": [],
        }
        result = format_message(test_data)

        assert "No OV movies" in result


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
