"""Scrapers for KinoWeek event sources.

This module provides modular scrapers for fetching events from:
1. Astor Grand Cinema (OV movies via JSON API)
2. Concert venues (Big events via HTML scraping)

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
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
)
from kinoweek.models import Event

if TYPE_CHECKING:
    from kinoweek.config import VenueConfig

__all__ = [
    "fetch_all_events",
    "AstorMovieScraper",
    "ConcertVenueScraper",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================


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
    - "20.11.2025 | 20:00 Uhr"

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

    # Try German date with time (e.g., "Fr, 22.11.2025 19:30" or "20.11.2025 | 20:00")
    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_str)
    if match:
        day, month, year = match.groups()
        # Try to find time
        time_match = re.search(r"(\d{1,2}):(\d{2})", date_str)
        if time_match:
            hour, minute = time_match.groups()
            return datetime(int(year), int(month), int(day), int(hour), int(minute))
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

            # Extract genres properly (filter empty strings)
            genre_names = [
                genres_map.get(gid, "")
                for gid in movie.get("genreIds", [])
            ]
            genre_names = [g for g in genre_names if g]  # Remove empty strings

            # Extract poster URL if available
            poster = movie.get("poster", {})
            poster_url = poster.get("src", "") if isinstance(poster, dict) else ""

            # Extract synopsis from translations
            synopsis = ""
            translations = movie.get("translations", [])
            if translations:
                # Prefer German, fall back to any available
                for trans in translations:
                    if trans.get("language") == "de":
                        synopsis = trans.get("descShort", "") or trans.get("descLong", "")
                        break
                if not synopsis and translations:
                    synopsis = translations[0].get("descShort", "") or translations[0].get("descLong", "")

            # Extract trailer URL (prefer 720p)
            trailer_url = ""
            trailers = movie.get("trailers", [])
            if trailers:
                for trailer in trailers:
                    if trailer.get("url720"):
                        trailer_url = trailer["url720"]
                        break
                    if trailer.get("url1080"):
                        trailer_url = trailer["url1080"]
                        break

            # Extract cast (directors and main actors)
            cast = []
            for person in movie.get("casts", []):
                cast.append({
                    "role": person.get("function", ""),
                    "name": person.get("name", ""),
                })

            # Build ticket URL with movie slug
            slug = movie.get("slug", "")
            ticket_url = f"https://hannover.premiumkino.de/film/{slug}" if slug else "https://hannover.premiumkino.de/"

            event = Event(
                title=title,
                date=datetime.fromisoformat(begin_str),
                venue=self.source_name,
                url=ticket_url,
                category="movie",
                metadata={
                    "duration": movie.get("minutes", 0),
                    "rating": movie.get("rating", 0),
                    "year": movie.get("year", 0),
                    "country": movie.get("country", ""),
                    "genres": genre_names,
                    "language": language,
                    "poster_url": poster_url,
                    "synopsis": synopsis,
                    "trailer_url": trailer_url,
                    "cast": cast,
                    "movie_id": movie_id,
                },
            )
            events.append(event)

        return events


# =============================================================================
# Concert Venue Scraper
# =============================================================================


class ConcertVenueScraper(BaseScraper):
    """Scraper for concert venues in Hannover.

    Fetches upcoming concerts and big events from multiple venue websites.
    Extracts detailed information including date, time, and ticket links.
    """

    def __init__(self, max_events_per_venue: int = 15) -> None:
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

            # Parse date from date-time element
            event_date = None
            time_str = "20:00"

            date_time_elem = item.select_one(".wpem-event-date-time-text")
            if date_time_elem:
                date_text = date_time_elem.get_text(strip=True)
                event_date = _parse_german_date(date_text)
                # Extract time if available
                time_match = re.search(r"(\d{1,2}):(\d{2})", date_text)
                if time_match:
                    time_str = f"{time_match.group(1)}:{time_match.group(2)}"

            if not event_date:
                # Fallback to day/month elements
                day_elem = item.select_one(".wpem-date")
                month_elem = item.select_one(".wpem-month")
                if not (day_elem and month_elem):
                    return None

                day = int(day_elem.get_text(strip=True))
                month_str = month_elem.get_text(strip=True).rstrip(".")
                month = GERMAN_MONTH_MAP.get(month_str.lower(), 1)
                # Use next year if month is before current month
                year = datetime.now().year
                if month < datetime.now().month:
                    year += 1
                event_date = datetime(year, month, day, 20, 0)

            # Extract URL
            link_elem = item.select_one("a.wpem-event-action-url")
            if not link_elem:
                return None
            event_url = link_elem.get("href", "")
            if not event_url.startswith("http"):
                event_url = f"https://www.zag-arena-hannover.de{event_url}"

            # Extract image URL if available
            img_elem = item.select_one("img")
            image_url = ""
            if img_elem:
                image_url = img_elem.get("src", "") or img_elem.get("data-src", "")
                if image_url and not image_url.startswith("http"):
                    image_url = f"https://www.zag-arena-hannover.de{image_url}"

            # Extract category from URL pattern if available
            category_type = "concert"  # default
            if "sport" in event_url.lower():
                category_type = "sport"
            elif "show" in event_url.lower() or "comedy" in event_url.lower():
                category_type = "show"

            return Event(
                title=title,
                date=event_date,
                venue=venue["name"],
                url=event_url,
                category="radar",
                metadata={
                    "time": time_str,
                    "event_type": category_type,
                    "image_url": image_url,
                    "address": "Expo Plaza 7, 30539 Hannover",
                },
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

            # Try to extract subtitle/description if available
            subtitle_elem = item.select_one(".hc-card-subtitle, .subtitle, p")
            subtitle = subtitle_elem.get_text(strip=True) if subtitle_elem else ""

            # Extract image URL
            img_elem = item.select_one("img")
            image_url = ""
            if img_elem:
                image_url = img_elem.get("src", "") or img_elem.get("data-src", "")
                if image_url and not image_url.startswith("http"):
                    image_url = f"{base_url}{image_url}"

            # Check for sold out status
            status = "available"
            status_elem = item.select_one(".sold-out, .ausverkauft, [class*='sold']")
            if status_elem:
                status = "sold_out"
            # Also check for text content
            item_text = item.get_text().lower()
            if "ausverkauft" in item_text or "sold out" in item_text:
                status = "sold_out"

            # Determine address based on venue
            address = ""
            if venue["name"] == "Swiss Life Hall":
                address = "Ferdinand-Wilhelm-Fricke-Weg 8, 30169 Hannover"
            elif venue["name"] == "Capitol Hannover":
                address = "Schwarzer Bär 2, 30449 Hannover"

            return Event(
                title=title,
                date=event_date,
                venue=venue["name"],
                url=event_url,
                category="radar",
                metadata={
                    "time": event_date.strftime("%H:%M"),
                    "subtitle": subtitle if subtitle != title else "",
                    "image_url": image_url,
                    "status": status,
                    "event_type": "concert",
                    "address": address,
                },
            )

        except Exception as exc:
            logger.debug("Error parsing %s event: %s", venue["name"], exc)
            return None


# =============================================================================
# Event Aggregation
# =============================================================================


def fetch_all_events() -> dict[str, list[Event]]:
    """Fetch and categorize events from all sources.

    Orchestrates all scrapers and categorizes events into:
    - Movies happening this week
    - Big events (concerts) on the radar

    Returns:
        Dictionary with categorized event lists.
    """
    today = datetime.now()
    next_week = today + timedelta(days=7)

    logger.info("Fetching events from all sources...")

    # Initialize scrapers
    movie_scraper = AstorMovieScraper()
    concert_scraper = ConcertVenueScraper(max_events_per_venue=15)

    # Fetch from all sources
    all_movies = movie_scraper.fetch()
    radar_events = concert_scraper.fetch()

    # Filter movies to this week only
    movies_this_week = sorted(
        (m for m in all_movies if m.is_this_week()),
        key=lambda e: e.date,
    )

    # Filter radar to EXCLUDE this week (future events only)
    big_events_radar = sorted(
        (r for r in radar_events if r.date > next_week),
        key=lambda e: e.date,
    )

    return {
        "movies_this_week": movies_this_week,
        "big_events_radar": big_events_radar,
    }


# Backward compatibility alias
get_all_events = fetch_all_events
