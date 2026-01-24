"""Tests for newly added venue sources: Broncos, Kulturpalast Linden, Weltspiele."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from boringhannover.constants import BERLIN_TZ
from boringhannover.sources.concerts.broncos import BroncosSource
from boringhannover.sources.concerts.kulturpalast_linden import (
    KulturpalastLindenSource,
)
from boringhannover.sources.concerts.weltspiele import WeltspieleSource


# =============================================================================
# BroncosSource Tests
# =============================================================================


class TestBroncosSource:
    """Tests for BroncosSource parsing."""

    def test_parses_valid_event_card(self) -> None:
        """Parse a complete event card with all fields."""
        html = """
        <article class="event">
          <a class="event__link" href="/event/test?date=2026-01-23">
            <div class="event__flex">
              <div class="event__left">
                <time class="event__start-time" datetime="2026-01-23T20:00:00+01:00">20:00</time>
              </div>
              <div class="event__content">
                <h3 class="event__title">Test Band</h3>
                <span class="event__tagline">Elektronische Musik</span>
              </div>
            </div>
          </a>
        </article>
        """
        soup = BeautifulSoup(html, "html.parser")
        source = BroncosSource()
        event = source._parse_event(soup.select_one("article.event"))

        assert event is not None
        assert event.title == "Test Band"
        assert event.venue == "Broncos"
        assert event.url.startswith("https://www.stadtkind-kalender.de/event/test")
        assert event.category == "radar"
        assert event.metadata.get("genre") == "Electronic"
        assert event.metadata.get("genre_source") == "stadtkind_tagline"
        assert event.metadata.get("time") == "20:00"
        assert event.metadata.get("address") == "Schwarzer Bär 7, 30449 Hannover"

    def test_parses_event_without_tagline(self) -> None:
        """Parse event card with missing genre tagline."""
        html = """
        <article class="event">
          <a class="event__link" href="/event/no-genre">
            <time class="event__start-time" datetime="2026-02-15T21:00:00+01:00">21:00</time>
            <h3 class="event__title">Mystery Artist</h3>
          </a>
        </article>
        """
        soup = BeautifulSoup(html, "html.parser")
        source = BroncosSource()
        event = source._parse_event(soup.select_one("article.event"))

        assert event is not None
        assert event.title == "Mystery Artist"
        assert event.metadata.get("genre") == ""
        assert event.metadata.get("genre_source") == ""

    def test_returns_none_for_missing_link(self) -> None:
        """Return None when event link is missing."""
        html = """
        <article class="event">
          <h3 class="event__title">No Link Event</h3>
        </article>
        """
        soup = BeautifulSoup(html, "html.parser")
        source = BroncosSource()
        event = source._parse_event(soup.select_one("article.event"))

        assert event is None

    def test_returns_none_for_missing_datetime(self) -> None:
        """Return None when datetime element is missing."""
        html = """
        <article class="event">
          <a class="event__link" href="/event/no-time">
            <h3 class="event__title">No Time Event</h3>
          </a>
        </article>
        """
        soup = BeautifulSoup(html, "html.parser")
        source = BroncosSource()
        event = source._parse_event(soup.select_one("article.event"))

        assert event is None

    def test_returns_none_for_missing_title(self) -> None:
        """Return None when title is missing."""
        html = """
        <article class="event">
          <a class="event__link" href="/event/no-title">
            <time class="event__start-time" datetime="2026-01-23T20:00:00+01:00">20:00</time>
          </a>
        </article>
        """
        soup = BeautifulSoup(html, "html.parser")
        source = BroncosSource()
        event = source._parse_event(soup.select_one("article.event"))

        assert event is None

    def test_parse_datetime_handles_timezone(self) -> None:
        """Parse ISO datetime and convert to Berlin timezone."""
        source = BroncosSource()

        # With explicit timezone
        dt = source._parse_datetime("2026-01-23T20:00:00+01:00")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.hour == 20

        # UTC time should be converted
        dt_utc = source._parse_datetime("2026-01-23T19:00:00+00:00")
        assert dt_utc is not None
        assert dt_utc.hour == 20  # UTC+1 in winter

    def test_parse_datetime_returns_none_for_invalid(self) -> None:
        """Return None for invalid datetime strings."""
        source = BroncosSource()

        assert source._parse_datetime("") is None
        assert source._parse_datetime("not-a-date") is None
        assert source._parse_datetime("2026-13-45") is None

    def test_relative_url_conversion(self) -> None:
        """Convert relative URLs to absolute."""
        html = """
        <article class="event">
          <a class="event__link" href="/event/relative-path">
            <time class="event__start-time" datetime="2026-01-23T20:00:00+01:00">20:00</time>
            <h3 class="event__title">Test</h3>
          </a>
        </article>
        """
        soup = BeautifulSoup(html, "html.parser")
        source = BroncosSource()
        event = source._parse_event(soup.select_one("article.event"))

        assert event is not None
        assert event.url == "https://www.stadtkind-kalender.de/event/relative-path"

    def test_max_events_limit(self) -> None:
        """Respect max_events limit when parsing."""
        # Create HTML with many events
        events_html = ""
        for i in range(50):
            events_html += f"""
            <article class="event">
              <a class="event__link" href="/event/{i}">
                <time class="event__start-time" datetime="2026-01-{(i % 28) + 1:02d}T20:00:00+01:00">20:00</time>
                <h3 class="event__title">Event {i}</h3>
              </a>
            </article>
            """
        soup = BeautifulSoup(events_html, "html.parser")
        source = BroncosSource()
        events = source._parse_events(soup)

        assert len(events) == source.max_events == 40


# =============================================================================
# KulturpalastLindenSource Tests
# =============================================================================


class TestKulturpalastLindenSource:
    """Tests for KulturpalastLindenSource parsing."""

    def test_parses_valid_ics_event(self) -> None:
        """Parse a valid iCalendar event."""
        ics_text = "\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Test//EN",
                "BEGIN:VEVENT",
                "DTSTART;TZID=Europe/Berlin:20260124T200000",
                "DTEND;TZID=Europe/Berlin:20260124T230000",
                "SUMMARY:Test Event",
                "DESCRIPTION:Line 1\\nLine 2\\nLine 3",
                "URL:https://example.com/event",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        source = KulturpalastLindenSource()
        events = source._parse_calendar(ics_text)

        assert len(events) == 1
        event = events[0]
        assert event.title == "Test Event"
        assert event.url == "https://example.com/event"
        assert event.venue == "Kulturpalast Linden"
        assert event.category == "radar"
        assert event.metadata.get("description") == "Line 1"
        assert event.metadata.get("time") == "20:00"

    def test_parses_event_without_url(self) -> None:
        """Use fallback URL when event URL is missing."""
        ics_text = "\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Test//EN",
                "BEGIN:VEVENT",
                "DTSTART:20260124T200000",
                "SUMMARY:No URL Event",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        source = KulturpalastLindenSource()
        events = source._parse_calendar(ics_text)

        assert len(events) == 1
        assert events[0].url == "https://kulturpalast-hannover.de/events/"

    def test_parses_all_day_event(self) -> None:
        """All-day events are parsed (ics library converts DATE to datetime)."""
        ics_text = "\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Test//EN",
                "BEGIN:VEVENT",
                "DTSTART;VALUE=DATE:20260124",
                "SUMMARY:All Day Event",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        source = KulturpalastLindenSource()
        events = source._parse_calendar(ics_text)

        assert len(events) == 1
        assert events[0].title == "All Day Event"
        # Note: ics library converts DATE to 00:00 UTC -> 01:00 Berlin
        # The all_day detection in _parse_event handles real ICS feeds correctly

    def test_sanitizes_cross_midnight_event(self) -> None:
        """Fix events where DTEND < DTSTART (cross-midnight)."""
        # Event starts at 22:00, ends at 02:00 next day
        # But ICS has same date for both (common bug)
        ics_text = "\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "BEGIN:VEVENT",
                "DTSTART:20260124T220000",
                "DTEND:20260124T020000",
                "SUMMARY:Late Night Party",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        source = KulturpalastLindenSource()
        sanitized = source._sanitize_ics(ics_text)

        # Should have bumped DTEND to next day
        assert "DTEND:20260125T020000" in sanitized

    def test_drops_invalid_date_range_event(self) -> None:
        """Drop events with invalid date ranges (DTEND before DTSTART, different dates)."""
        ics_text = "\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "BEGIN:VEVENT",
                "DTSTART:20260125T220000",
                "DTEND:20260124T020000",
                "SUMMARY:Invalid Event",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        source = KulturpalastLindenSource()
        sanitized = source._sanitize_ics(ics_text)

        # Invalid event should be dropped entirely
        assert "Invalid Event" not in sanitized

    def test_handles_malformed_ics(self) -> None:
        """Return empty list for completely malformed ICS."""
        source = KulturpalastLindenSource()
        events = source._parse_calendar("not valid ics data at all")

        assert events == []

    def test_skips_events_without_title(self) -> None:
        """Skip events with empty or missing title."""
        ics_text = "\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "BEGIN:VEVENT",
                "DTSTART:20260124T200000",
                "SUMMARY:",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        source = KulturpalastLindenSource()
        events = source._parse_calendar(ics_text)

        assert events == []

    def test_first_description_line_extraction(self) -> None:
        """Extract first non-empty line from description."""
        source = KulturpalastLindenSource()

        assert source._first_description_line("First line\\nSecond") == "First line"
        assert source._first_description_line("  \\nActual first") == "Actual first"
        assert source._first_description_line("") is None
        assert source._first_description_line("   ") is None

        # Long lines get truncated
        long_line = "x" * 300
        result = source._first_description_line(long_line)
        assert result is not None
        assert len(result) == 200

    def test_events_sorted_by_date(self) -> None:
        """Events should be sorted by start date."""
        ics_text = "\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Test//EN",
                "BEGIN:VEVENT",
                "DTSTART:20260130T200000",
                "SUMMARY:Later Event",
                "END:VEVENT",
                "BEGIN:VEVENT",
                "DTSTART:20260124T200000",
                "SUMMARY:Earlier Event",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        source = KulturpalastLindenSource()
        events = source._parse_calendar(ics_text)

        assert len(events) == 2
        assert events[0].title == "Earlier Event"
        assert events[1].title == "Later Event"


# =============================================================================
# WeltspieleSource Tests
# =============================================================================


class TestWeltspieleSource:
    """Tests for WeltspieleSource parsing."""

    def test_parses_show_date_with_time(self) -> None:
        """Parse show-date string with time range."""
        source = WeltspieleSource()
        dt = source._parse_show_date("Sat 27 January 22:00-10:00")

        assert dt is not None
        assert dt.month == 1
        assert dt.day == 27
        assert dt.hour == 22
        assert dt.minute == 0

    def test_parses_show_date_german_month(self) -> None:
        """Parse show-date with German month name."""
        source = WeltspieleSource()
        dt = source._parse_show_date("Sa 15 Februar 21:00")

        assert dt is not None
        assert dt.month == 2
        assert dt.day == 15
        assert dt.hour == 21

    def test_parse_show_date_returns_none_for_invalid(self) -> None:
        """Return None for unparseable show-date strings."""
        source = WeltspieleSource()

        assert source._parse_show_date("") is None
        assert source._parse_show_date("No date here") is None
        assert source._parse_show_date("27 January") is None  # No time

    def test_parse_month_english(self) -> None:
        """Parse English month names."""
        source = WeltspieleSource()

        assert source._parse_month("January") == 1
        assert source._parse_month("DECEMBER") == 12
        assert source._parse_month("march") == 3

    def test_parse_month_german(self) -> None:
        """Parse German month names."""
        source = WeltspieleSource()

        assert source._parse_month("Januar") == 1
        assert source._parse_month("Dezember") == 12
        assert source._parse_month("März") == 3

    def test_parse_month_returns_none_for_invalid(self) -> None:
        """Return None for invalid month names."""
        source = WeltspieleSource()

        assert source._parse_month("") is None
        assert source._parse_month("NotAMonth") is None

    def test_compose_date_future_aware(self) -> None:
        """Compose date rolls to next year if date is in past."""
        source = WeltspieleSource()
        today = datetime.now(BERLIN_TZ)

        # A date clearly in the past this year should roll to next year
        past_month = today.month - 2 if today.month > 2 else 10
        dt = source._compose_date(15, past_month)

        assert dt is not None
        if past_month < today.month:
            assert dt.year == today.year + 1

    def test_compose_date_invalid(self) -> None:
        """Return None for invalid day/month combinations."""
        source = WeltspieleSource()

        assert source._compose_date(31, 2) is None  # Feb 31
        assert source._compose_date(0, 5) is None  # Day 0

    def test_extract_title_skips_rich_text_box(self) -> None:
        """Skip elements with underline-rich-text-box class."""
        html = """
        <li class="program-event">
          <div class="underline underline-rich-text-box">Support Act</div>
          <div class="underline">Main Artist</div>
        </li>
        """
        soup = BeautifulSoup(html, "html.parser")
        source = WeltspieleSource()
        title = source._extract_title(soup.select_one("li.program-event"))

        assert title == "Main Artist"

    def test_extract_lineup(self) -> None:
        """Extract lineup from rich text boxes."""
        html = """
        <li class="program-event">
          <div class="program-event-place">
            <span class="underline-rich-text-box">DJ One</span>
            <span class="underline-rich-text-box">DJ Two</span>
          </div>
        </li>
        """
        soup = BeautifulSoup(html, "html.parser")
        source = WeltspieleSource()
        lineup = source._extract_lineup(soup.select_one("li.program-event"))

        assert lineup == "DJ One DJ Two"

    def test_extract_lineup_returns_none_when_empty(self) -> None:
        """Return None when no lineup elements found."""
        html = '<li class="program-event"></li>'
        soup = BeautifulSoup(html, "html.parser")
        source = WeltspieleSource()
        lineup = source._extract_lineup(soup.select_one("li.program-event"))

        assert lineup is None

    def test_parse_program_event(self) -> None:
        """Parse a program event from the listing page."""
        html = """
        <a href="/event/test-party">
          <li class="program-event">
            <div class="program-event-header">
              <span class="in-brackets">Fr 24</span>
            </div>
            <span class="program-event-tag">Party</span>
            <div class="underline">Test Party Night</div>
          </li>
        </a>
        """
        soup = BeautifulSoup(html, "html.parser")
        source = WeltspieleSource()
        entry = source._parse_program_event(soup.select_one("li.program-event"), 1)

        assert entry is not None
        assert entry.title == "Test Party Night"
        assert entry.day == 24
        assert entry.month == 1
        assert entry.tag == "Party"
        assert entry.url == "https://weltspiele.club/event/test-party"

    def test_parse_program_event_no_link(self) -> None:
        """Return None when event has no parent link."""
        html = """
        <li class="program-event">
          <div class="program-event-header">
            <span class="in-brackets">Fr 24</span>
          </div>
          <div class="underline">Orphan Event</div>
        </li>
        """
        soup = BeautifulSoup(html, "html.parser")
        source = WeltspieleSource()
        entry = source._parse_program_event(soup.select_one("li.program-event"), 1)

        assert entry is None

    def test_build_event_uses_fallback_time(self) -> None:
        """Use 22:00 fallback when event page doesn't have time."""
        source = WeltspieleSource()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>No show-date here</body></html>"
        mock_client.get.return_value = mock_response

        from boringhannover.sources.concerts.weltspiele import _ProgramEntry

        entry = _ProgramEntry(
            title="Test",
            day=24,
            month=1,
            url="https://weltspiele.club/event/test",
            tag="Club",
            lineup=None,
        )
        event = source._build_event(mock_client, entry)

        assert event is not None
        assert event.metadata.get("time") == "22:00"
        assert event.date.hour == 22

    def test_build_event_handles_failed_page_request(self) -> None:
        """Fall back to program URL when event page returns error."""
        source = WeltspieleSource()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = ""
        mock_client.get.return_value = mock_response

        from boringhannover.sources.concerts.weltspiele import _ProgramEntry

        entry = _ProgramEntry(
            title="Test",
            day=24,
            month=1,
            url="https://weltspiele.club/event/broken",
            tag=None,
            lineup=None,
        )
        event = source._build_event(mock_client, entry)

        assert event is not None
        assert event.url == "https://weltspiele.club/programm/"
        assert event.metadata.get("event_type") == "club"


# =============================================================================
# Integration / Registration Tests
# =============================================================================


class TestSourceRegistration:
    """Test that sources are properly registered."""

    def test_sources_registered(self) -> None:
        """All new sources should be in the registry."""
        from boringhannover.sources.base import get_all_sources

        sources = get_all_sources()

        assert "broncos" in sources
        assert "kulturpalast_linden" in sources
        assert "weltspiele" in sources

    def test_source_types_correct(self) -> None:
        """All sources should have correct source_type."""
        assert BroncosSource.source_type == "concert"
        assert KulturpalastLindenSource.source_type == "concert"
        assert WeltspieleSource.source_type == "concert"

    def test_source_names_set(self) -> None:
        """All sources should have human-readable names."""
        assert BroncosSource.source_name == "Broncos"
        assert KulturpalastLindenSource.source_name == "Kulturpalast Linden"
        assert WeltspieleSource.source_name == "Weltspiele"

    def test_sources_have_addresses(self) -> None:
        """All sources should define an address."""
        assert "Hannover" in BroncosSource.ADDRESS
        assert "Hannover" in KulturpalastLindenSource.ADDRESS
        assert "Hannover" in WeltspieleSource.ADDRESS
