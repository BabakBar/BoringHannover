"""Scrapers for KinoWeek event sources.

This module provides modular scrapers for fetching events from:
1. Astor Grand Cinema (OV movies via JSON API)
2. Staatstheater Hannover (Opera/Ballet via HTML scraping)
3. Concert venues (Big events via HTML scraping)

Each scraper is implemented as a class with a consistent interface,
and helper functions handle common operations like date parsing.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import httpx
from bs4 import BeautifulSoup

from kinoweek.config import (
    ASTOR_API_URL,
    CONCERT_VENUES,
    GERMAN_MONTH_MAP,
    IGNORE_KEYWORDS,
    REQUEST_TIMEOUT_SECONDS,
    STAATSTHEATER_CALENDAR_URL,
    USER_AGENT,
)
from kinoweek.models import Event

if TYPE_CHECKING:
    from collections.abc import Sequence

    from kinoweek.config import VenueConfig

__all__ = [
    "fetch_all_events",
    "AstorMovieScraper",
    "StaatstheaterScraper",
    "ConcertVenueScraper",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================


def _should_filter_event(title: str) -> bool:
    """Check if event should be filtered out based on keywords.

    Args:
        title: Event title to check.

    Returns:
        True if event should be excluded, False otherwise.
    """
    title_lower = title.lower()
    return any(keyword.lower() in title_lower for keyword in IGNORE_KEYWORDS)


def _is_original_version(language: str) -> bool:
    """Determine if a movie showing is in original version (OV).

    OV movies are those NOT dubbed in German, including:
    - Movies in English, Japanese, Italian, Spanish, Russian, etc.
    - Movies with German subtitles (indicated by "Untertitel:")

    NOT OV:
    - Movies with "Sprache: Deutsch" without subtitles (German dubs)

    Args:
        language: Language string from the API (e.g., "Sprache: Englisch").

    Returns:
        True if this is an original version showing.
    """
    if not language:
        return False

    # German language is only OV if it has subtitles (foreign film with German subs)
    if "Deutsch" in language:
        return "Untertitel:" in language

    # All other languages are original versions
    return True


def _parse_german_date(date_str: str) -> datetime | None:
    """Parse various German date formats into datetime.

    Handles formats like:
    - "20.11.2025"
    - "Fr, 22.11.2025 19:30"
    - "AB22NOV2025"

    Args:
        date_str: Date string in German format.

    Returns:
        Parsed datetime or None if parsing fails.
    """
    # Try ISO format first
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d.%m.%Y %H:%M",
    ):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    # Try German date with time (e.g., "Fr, 22.11.2025 19:30")
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})\s*(\d{2}):(\d{2})", date_str)
    if match:
        day, month, year, hour, minute = match.groups()
        return datetime(int(year), int(month), int(day), int(hour), int(minute))

    # Try date only (e.g., "22.11.2025")
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", date_str)
    if match:
        day, month, year = match.groups()
        return datetime(int(year), int(month), int(day), 20, 0)  # Default 8 PM

    return None


def _parse_venue_date(date_str: str) -> datetime | None:
    """Parse venue-specific date formats.

    Handles formats like:
    - "AB22NOV2025" (concert venues)
    - "22 Nov" with separate year

    Args:
        date_str: Date string from venue page.

    Returns:
        Parsed datetime or None if parsing fails.
    """
    # Pattern: day + month name + year (e.g., "22NOV2025")
    match = re.search(r"(\d{1,2})([A-ZÄÖÜa-zäöü]+)(\d{4})", date_str)
    if match:
        day, month_str, year = match.groups()
        month = GERMAN_MONTH_MAP.get(month_str.lower(), 1)
        return datetime(int(year), month, int(day), 20, 0)  # Default 8 PM

    return None


def _create_http_client() -> httpx.Client:
    """Create a configured HTTP client with standard headers.

    Returns:
        Configured httpx.Client instance.
    """
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )


# =============================================================================
# Base Scraper Class
# =============================================================================


class BaseScraper(ABC):
    """Abstract base class for event scrapers.

    Provides common interface and shared functionality for all scrapers.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of this event source."""

    @abstractmethod
    def fetch(self) -> list[Event]:
        """Fetch events from the source.

        Returns:
            List of Event objects from this source.
        """


# =============================================================================
# Astor Movie Scraper
# =============================================================================


class AstorMovieScraper(BaseScraper):
    """Scraper for Astor Grand Cinema Hannover.

    Fetches OV (original version) movie showtimes via the cinema's JSON API.
    Filters out German-dubbed versions to only include original language films.
    """

    @property
    def source_name(self) -> str:
        return "Astor Grand Cinema"

    def fetch(self) -> list[Event]:
        """Fetch OV movie showtimes from Astor API.

        Returns:
            List of Event objects with category="movie".
        """
        events: list[Event] = []

        try:
            logger.info("Fetching movies from %s", self.source_name)

            with _create_http_client() as client:
                client.headers.update({
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json; charset=utf-8",
                    "Referer": "https://hannover.premiumkino.de/",
                })
                response = client.get(ASTOR_API_URL)
                response.raise_for_status()
                data = response.json()

            events = self._parse_response(data)
            logger.info("Found %d OV movie showtimes", len(events))

        except httpx.RequestError as exc:
            logger.exception("Astor API request failed: %s", exc)
            raise

        return events

    def _parse_response(self, data: dict) -> list[Event]:
        """Parse the Astor API response into Event objects.

        Args:
            data: JSON response from the API.

        Returns:
            List of parsed Event objects.
        """
        events: list[Event] = []

        # Build lookup tables
        genres_map = {g["id"]: g["name"] for g in data.get("genres", [])}
        movies_map = {m["id"]: m for m in data.get("movies", [])}

        for performance in data.get("performances", []):
            movie_id = performance.get("movieId")
            if movie_id not in movies_map:
                continue

            movie = movies_map[movie_id]
            title = movie.get("name", "Unknown")
            language = performance.get("language", "")

            # Filter for Original Version only
            if not _is_original_version(language):
                logger.debug("Skipping non-OV: %s (%s)", title, language)
                continue

            begin_str = performance.get("begin")
            if not begin_str:
                continue

            event = Event(
                title=title,
                date=datetime.fromisoformat(begin_str),
                venue=self.source_name,
                url="https://hannover.premiumkino.de/",
                category="movie",
                metadata={
                    "duration": movie.get("minutes", 0),
                    "rating": movie.get("rating", 0),
                    "year": movie.get("year", 0),
                    "country": movie.get("country", ""),
                    "genres": [
                        genres_map.get(gid, "")
                        for gid in movie.get("genreIds", [])
                    ],
                    "language": language,
                },
            )
            events.append(event)

        return events


# =============================================================================
# Staatstheater Scraper
# =============================================================================


class StaatstheaterScraper(BaseScraper):
    """Scraper for Staatstheater Hannover.

    Fetches opera, ballet, and theater events via HTML scraping.
    """

    def __init__(self, start_date: datetime, end_date: datetime) -> None:
        """Initialize with date range for filtering.

        Args:
            start_date: Start of date range to fetch.
            end_date: End of date range to fetch.
        """
        self._start_date = start_date
        self._end_date = end_date

    @property
    def source_name(self) -> str:
        return "Staatstheater Hannover"

    def fetch(self) -> list[Event]:
        """Fetch culture events from Staatstheater calendar.

        Returns:
            List of Event objects with category="culture".
        """
        events: list[Event] = []

        try:
            logger.info("Fetching events from %s", self.source_name)

            with _create_http_client() as client:
                response = client.get(STAATSTHEATER_CALENDAR_URL)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

            events = self._parse_html(soup)
            logger.info("Found %d culture events", len(events))

        except httpx.RequestError as exc:
            logger.warning("Staatstheater request failed: %s", exc)
        except Exception as exc:
            logger.warning("Staatstheater scraping failed: %s", exc)

        return events

    def _parse_html(self, soup: BeautifulSoup) -> list[Event]:
        """Parse the calendar HTML into Event objects.

        Args:
            soup: Parsed HTML document.

        Returns:
            List of parsed Event objects.
        """
        events: list[Event] = []
        event_items = soup.select("article.event, .event-item, article")

        if not event_items:
            logger.warning("No event items found on Staatstheater page")
            return events

        for item in event_items:
            event = self._parse_event_item(item)
            if event:
                events.append(event)

        return events

    def _parse_event_item(self, item: BeautifulSoup) -> Event | None:
        """Parse a single event item from the HTML.

        Args:
            item: BeautifulSoup element representing one event.

        Returns:
            Parsed Event or None if parsing fails.
        """
        try:
            # Extract title
            title_elem = item.select_one("h2, h3, h4, .title, .event-title")
            if not title_elem:
                return None
            title = title_elem.get_text(strip=True)

            # Filter by keywords
            if _should_filter_event(title):
                logger.debug("Filtering out: %s", title)
                return None

            # Extract and parse date
            date_elem = item.select_one("time, .date, .event-date, .datetime")
            if not date_elem:
                return None

            date_str = date_elem.get("datetime") or date_elem.get_text(strip=True)
            event_date = _parse_german_date(date_str)

            if not event_date:
                logger.debug("Could not parse date: %s", date_str)
                return None

            # Filter by date range
            if not (self._start_date <= event_date <= self._end_date):
                return None

            # Extract venue
            venue_elem = item.select_one(".venue, .location, .event-venue")
            venue = (
                venue_elem.get_text(strip=True)
                if venue_elem
                else self.source_name
            )

            # Extract URL
            link_elem = item.select_one("a")
            event_url = (
                link_elem.get("href") if link_elem else STAATSTHEATER_CALENDAR_URL
            )
            if event_url.startswith("/"):
                event_url = f"https://staatstheater-hannover.de{event_url}"

            return Event(
                title=title,
                date=event_date,
                venue=venue,
                url=event_url,
                category="culture",
            )

        except Exception as exc:
            logger.debug("Error parsing Staatstheater event: %s", exc)
            return None


# =============================================================================
# Concert Venue Scraper
# =============================================================================


class ConcertVenueScraper(BaseScraper):
    """Scraper for concert venues in Hannover.

    Fetches upcoming concerts and big events from multiple venue websites.
    """

    def __init__(self, max_events_per_venue: int = 10) -> None:
        """Initialize with event limit.

        Args:
            max_events_per_venue: Maximum events to fetch per venue.
        """
        self._max_events = max_events_per_venue

    @property
    def source_name(self) -> str:
        return "Concert Venues"

    def fetch(self) -> list[Event]:
        """Fetch concert events from all enabled venues.

        Returns:
            List of Event objects with category="radar".
        """
        events: list[Event] = []
        enabled_venues = [v for v in CONCERT_VENUES if v.get("enabled", False)]

        if not enabled_venues:
            logger.info("No concert venues enabled")
            return events

        for venue in enabled_venues:
            venue_events = self._fetch_venue(venue)
            events.extend(venue_events)

        return events

    def _fetch_venue(self, venue: VenueConfig) -> list[Event]:
        """Fetch events from a single venue.

        Args:
            venue: Venue configuration.

        Returns:
            List of events from this venue.
        """
        events: list[Event] = []
        venue_name = venue["name"]

        try:
            logger.info("Fetching concerts from %s", venue_name)

            with _create_http_client() as client:
                response = client.get(venue["url"])
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

            if venue_name == "ZAG Arena":
                events = self._parse_zag_arena(soup, venue)
            elif venue_name in ("Swiss Life Hall", "Capitol Hannover"):
                events = self._parse_hc_venue(soup, venue)

            logger.info("Found %d events from %s", len(events), venue_name)

        except httpx.RequestError as exc:
            logger.warning("%s request failed: %s", venue_name, exc)
        except Exception as exc:
            logger.warning("%s scraping failed: %s", venue_name, exc)

        return events

    def _parse_zag_arena(
        self, soup: BeautifulSoup, venue: VenueConfig
    ) -> list[Event]:
        """Parse ZAG Arena event listing.

        Args:
            soup: Parsed HTML document.
            venue: Venue configuration.

        Returns:
            List of parsed Event objects.
        """
        events: list[Event] = []
        selectors = venue["selectors"]
        event_items = soup.select(selectors.get("event", ".wpem-event-layout-wrapper"))

        for item in event_items[: self._max_events]:
            event = self._parse_zag_event(item, venue)
            if event:
                events.append(event)

        return events

    def _parse_zag_event(
        self, item: BeautifulSoup, venue: VenueConfig
    ) -> Event | None:
        """Parse a single ZAG Arena event.

        Args:
            item: BeautifulSoup element representing one event.
            venue: Venue configuration.

        Returns:
            Parsed Event or None if parsing fails.
        """
        try:
            # Extract title
            title_elem = item.select_one(".wpem-heading-text")
            if not title_elem:
                return None
            title = title_elem.get_text(strip=True)

            if _should_filter_event(title):
                return None

            # Parse date from date-time element
            date_time_elem = item.select_one(".wpem-event-date-time-text")
            if date_time_elem:
                date_str = date_time_elem.get_text(strip=True)
                event_date = _parse_german_date(date_str)
            else:
                # Fallback to day/month elements
                day_elem = item.select_one(".wpem-date")
                month_elem = item.select_one(".wpem-month")
                if not (day_elem and month_elem):
                    return None

                day = int(day_elem.get_text(strip=True))
                month_str = month_elem.get_text(strip=True).rstrip(".")
                month = GERMAN_MONTH_MAP.get(month_str.lower(), 1)
                event_date = datetime(datetime.now().year, month, day, 20, 0)

            if not event_date:
                return None

            # Extract URL
            link_elem = item.select_one("a.wpem-event-action-url")
            if not link_elem:
                return None
            event_url = link_elem.get("href", "")
            if not event_url.startswith("http"):
                event_url = f"https://www.zag-arena-hannover.de{event_url}"

            return Event(
                title=title,
                date=event_date,
                venue=venue["name"],
                url=event_url,
                category="radar",
            )

        except Exception as exc:
            logger.debug("Error parsing ZAG Arena event: %s", exc)
            return None

    def _parse_hc_venue(
        self, soup: BeautifulSoup, venue: VenueConfig
    ) -> list[Event]:
        """Parse Swiss Life Hall or Capitol event listing.

        Both venues use the same "hc-kartenleger" card system.

        Args:
            soup: Parsed HTML document.
            venue: Venue configuration.

        Returns:
            List of parsed Event objects.
        """
        events: list[Event] = []
        selectors = venue["selectors"]
        event_items = soup.select(selectors.get("event", "a.hc-card-link-wrapper"))

        base_url = (
            "https://www.swisslife-hall.de"
            if venue["name"] == "Swiss Life Hall"
            else "https://www.capitol-hannover.de"
        )

        for item in event_items[: self._max_events]:
            event = self._parse_hc_event(item, venue, base_url)
            if event:
                events.append(event)

        return events

    def _parse_hc_event(
        self, item: BeautifulSoup, venue: VenueConfig, base_url: str
    ) -> Event | None:
        """Parse a single HC-style venue event.

        Args:
            item: BeautifulSoup element representing one event.
            venue: Venue configuration.
            base_url: Base URL for relative links.

        Returns:
            Parsed Event or None if parsing fails.
        """
        try:
            # Extract title from 'title' attribute or h4/h3
            title = item.get("title")
            if not title:
                title_elem = item.select_one("h4, h3")
                title = title_elem.get_text(strip=True) if title_elem else None
            if not title:
                return None

            if _should_filter_event(title):
                return None

            # Parse date from time element (format: "AB22NOV2025")
            date_elem = item.select_one("time")
            if not date_elem:
                return None

            date_str = date_elem.get_text(strip=True)
            event_date = _parse_venue_date(date_str)
            if not event_date:
                return None

            # Extract URL
            event_url = item.get("href", "")
            if not event_url.startswith("http"):
                event_url = f"{base_url}{event_url}"

            return Event(
                title=title,
                date=event_date,
                venue=venue["name"],
                url=event_url,
                category="radar",
            )

        except Exception as exc:
            logger.debug("Error parsing %s event: %s", venue["name"], exc)
            return None


# =============================================================================
# Event Aggregation
# =============================================================================


class EventData:
    """Container for categorized event data."""

    def __init__(
        self,
        movies_this_week: Sequence[Event],
        culture_this_week: Sequence[Event],
        big_events_radar: Sequence[Event],
    ) -> None:
        self.movies_this_week = list(movies_this_week)
        self.culture_this_week = list(culture_this_week)
        self.big_events_radar = list(big_events_radar)

    def to_dict(self) -> dict[str, list[Event]]:
        """Convert to dictionary format for backward compatibility."""
        return {
            "movies_this_week": self.movies_this_week,
            "culture_this_week": self.culture_this_week,
            "big_events_radar": self.big_events_radar,
        }


def fetch_all_events() -> dict[str, list[Event]]:
    """Fetch and categorize events from all sources.

    Orchestrates all scrapers and categorizes events into:
    - Movies happening this week
    - Culture events happening this week
    - Big events beyond this week (on the radar)

    Returns:
        Dictionary with categorized event lists.
    """
    today = datetime.now()
    next_week = today + timedelta(days=7)

    logger.info("Fetching events from all sources...")

    # Initialize scrapers
    movie_scraper = AstorMovieScraper()
    culture_scraper = StaatstheaterScraper(start_date=today, end_date=next_week)
    concert_scraper = ConcertVenueScraper(max_events_per_venue=10)

    # Fetch from all sources
    all_movies = movie_scraper.fetch()
    culture_events = culture_scraper.fetch()
    radar_events = concert_scraper.fetch()

    # Filter movies to this week only
    movies_this_week = sorted(
        (m for m in all_movies if m.is_this_week()),
        key=lambda e: e.date,
    )

    # Culture events are already filtered by date range
    culture_this_week = sorted(culture_events, key=lambda e: e.date)

    # Filter radar to EXCLUDE this week (future events only)
    big_events_radar = sorted(
        (r for r in radar_events if r.date > next_week),
        key=lambda e: e.date,
    )

    return {
        "movies_this_week": movies_this_week,
        "culture_this_week": culture_this_week,
        "big_events_radar": big_events_radar,
    }


# Backward compatibility alias
get_all_events = fetch_all_events
