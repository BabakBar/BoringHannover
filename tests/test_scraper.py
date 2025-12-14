"""Tests for BoringHannover scraper functionality.

Tests cover the core modules:
- models: Event dataclass and methods
- scrapers: Event fetching and parsing
- notifier: Message formatting and Telegram integration
- main: CLI and workflow orchestration
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from boringhannover.aggregator import fetch_all_events
from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.notifier import format_message, notify
from boringhannover.sources.cinema.astor import AstorSource as AstorMovieScraper
from boringhannover.sources.concerts.zag_arena import (
    ZAGArenaSource as ConcertVenueScraper,
)

# =============================================================================
# Event Model Tests
# =============================================================================


class TestEventModel:
    """Tests for the Event dataclass."""

    def test_event_creation(self) -> None:
        """Test basic event creation with required fields."""
        event = Event(
            title="Test Movie",
            date=datetime.now(BERLIN_TZ),
            venue="Test Venue",
            url="https://example.com",
            category="movie",
        )
        assert event.title == "Test Movie"
        assert event.venue == "Test Venue"
        assert event.category == "movie"
        assert event.metadata == {}

    def test_event_with_metadata(self) -> None:
        """Test event creation with metadata."""
        metadata = {"duration": 120, "rating": 12}
        event = Event(
            title="Test Movie",
            date=datetime.now(BERLIN_TZ),
            venue="Test Venue",
            url="https://example.com",
            category="movie",
            metadata=metadata,
        )
        assert event.metadata["duration"] == 120
        assert event.metadata["rating"] == 12

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
        naive = datetime(2025, 12, 12, 19, 30, tzinfo=BERLIN_TZ)
        event = Event(
            title="Naive Date",
            date=naive,
            venue="Venue",
            url="https://example.com",
            category="movie",
        )
        assert event.date.tzinfo is BERLIN_TZ

    def test_event_valid_categories(self) -> None:
        """Test that valid categories work correctly."""
        for category in ("movie", "culture", "radar"):
            event = Event(
                title="Test",
                date=datetime.now(BERLIN_TZ),
                venue="Venue",
                url="https://example.com",
                category=category,
            )
            assert event.category == category


# =============================================================================
# Scraper Tests
# =============================================================================


class TestAstorMovieScraper:
    """Tests for the Astor movie scraper."""

    def test_scraper_source_name(self) -> None:
        """Test scraper returns correct source name."""
        scraper = AstorMovieScraper()
        assert scraper.source_name == "Astor Grand Cinema"

    @patch("boringhannover.sources.base.httpx.Client")
    def test_fetch_returns_list(self, mock_client: Mock) -> None:
        """Test that fetch returns a list of events."""
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "genres": [],
            "movies": [],
            "performances": [],
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        scraper = AstorMovieScraper()
        result = scraper.fetch()

        assert isinstance(result, list)

    @patch("boringhannover.sources.base.httpx.Client")
    def test_fetch_parses_movies(self, mock_client: Mock) -> None:
        """Test that fetch correctly parses movie data."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "genres": [{"id": 1, "name": "Drama"}],
            "movies": [
                {
                    "id": 100,
                    "name": "Test Movie",
                    "minutes": 120,
                    "rating": 12,
                    "year": 2024,
                    "country": "US",
                    "genreIds": [1],
                }
            ],
            "performances": [
                {
                    "movieId": 100,
                    "begin": "2024-11-24T19:30:00",
                    "language": "Sprache: Englisch",
                }
            ],
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        scraper = AstorMovieScraper()
        result = scraper.fetch()

        assert len(result) == 1
        assert result[0].title == "Test Movie"
        assert result[0].category == "movie"
        assert result[0].metadata["duration"] == 120

    @patch("boringhannover.sources.base.httpx.Client")
    def test_fetch_filters_german_dubs(self, mock_client: Mock) -> None:
        """Test that German dubbed movies are filtered out."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "genres": [],
            "movies": [{"id": 100, "name": "Test Movie"}],
            "performances": [
                {
                    "movieId": 100,
                    "begin": "2024-11-24T19:30:00",
                    "language": "Sprache: Deutsch",  # German dub, should be filtered
                }
            ],
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        scraper = AstorMovieScraper()
        result = scraper.fetch()

        assert len(result) == 0


class TestConcertVenueScraper:
    """Tests for the concert venue scraper (ZAG Arena)."""

    def test_scraper_source_name(self) -> None:
        """Test scraper returns correct source name."""
        scraper = ConcertVenueScraper()
        assert scraper.source_name == "ZAG Arena"

    def test_scraper_max_events(self) -> None:
        """Test scraper has max events limit configured."""
        scraper = ConcertVenueScraper()
        assert scraper.max_events == 15


class TestFetchAllEvents:
    """Tests for the event aggregation function."""

    @patch("boringhannover.aggregator.get_all_sources")
    def test_returns_categorized_dict(
        self,
        mock_get_sources: Mock,
    ) -> None:
        """Test that fetch_all_events returns correctly structured data."""
        # Mock the source registry to return empty sources
        mock_source = Mock()
        mock_source.return_value.enabled = True
        mock_source.return_value.fetch.return_value = []
        mock_get_sources.return_value = {"mock_source": mock_source}

        result = fetch_all_events()

        assert "movies_this_week" in result
        assert "big_events_radar" in result
        assert isinstance(result["movies_this_week"], list)
        assert isinstance(result["big_events_radar"], list)

    @patch("boringhannover.aggregator.get_all_sources")
    def test_handles_naive_datetimes_from_sources(self, mock_get_sources: Mock) -> None:
        """Sources may emit naive datetimes; aggregation should not crash."""
        today = datetime.now(BERLIN_TZ)

        movie_event = Event(
            title="Movie",
            date=(today + timedelta(days=1)).replace(tzinfo=None),
            venue="Venue",
            url="https://example.com",
            category="movie",
        )
        radar_event = Event(
            title="Concert",
            date=(today + timedelta(days=8)).replace(tzinfo=None),
            venue="Venue",
            url="https://example.com",
            category="radar",
        )

        movie_source = Mock()
        movie_source.return_value.enabled = True
        movie_source.return_value.fetch.return_value = [movie_event]

        radar_source = Mock()
        radar_source.return_value.enabled = True
        radar_source.return_value.fetch.return_value = [radar_event]

        mock_get_sources.return_value = {
            "movie": movie_source,
            "radar": radar_source,
        }

        result = fetch_all_events()

        assert len(result["movies_this_week"]) == 1
        assert len(result["big_events_radar"]) == 1


# =============================================================================
# Notifier Tests
# =============================================================================


class TestFormatMessage:
    """Tests for message formatting."""

    def test_format_message_returns_string(self) -> None:
        """Test that format_message returns a string."""
        test_data = {
            "movies_this_week": [],
            "big_events_radar": [],
        }
        result = format_message(test_data)
        assert isinstance(result, str)

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

        assert isinstance(result, str)
        assert "No OV movies" in result


class TestNotify:
    """Tests for the main notify function."""

    @patch("boringhannover.notifier.save_to_file")
    @patch("boringhannover.notifier.save_all_formats")
    def test_notify_saves_to_files(
        self, mock_save_all: Mock, mock_save: Mock
    ) -> None:
        """Test notify saves data to files."""
        mock_save_all.return_value = {}
        test_data = {
            "movies_this_week": [],
            "big_events_radar": [],
        }

        result = notify(test_data)

        assert result is True
        mock_save.assert_called_once()
        mock_save_all.assert_called_once()


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the complete workflow."""

    @patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "test_chat"},
    )
    @patch("boringhannover.main.notify")
    @patch("boringhannover.main.fetch_all_events")
    def test_full_workflow(self, mock_fetch: Mock, mock_notify: Mock) -> None:
        """Test the complete scraping and notification workflow."""
        from boringhannover.main import run  # noqa: PLC0415

        mock_fetch.return_value = {
            "movies_this_week": [],
            "big_events_radar": [],
        }
        mock_notify.return_value = True

        result = run()

        assert result is True
        mock_fetch.assert_called_once()
        mock_notify.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
