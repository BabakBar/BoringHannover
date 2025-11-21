"""Configuration settings for KinoWeek scrapers.

All URLs, selectors, and settings are centralized here for easy maintenance.
Uses TypedDict for structured configuration and Final for immutable constants.
"""

from __future__ import annotations

from typing import Final, TypedDict

__all__ = [
    "ASTOR_API_URL",
    "STAATSTHEATER_CALENDAR_URL",
    "CONCERT_VENUES",
    "IGNORE_KEYWORDS",
    "REQUEST_TIMEOUT_SECONDS",
    "USER_AGENT",
    "TELEGRAM_MESSAGE_MAX_LENGTH",
]


# =============================================================================
# API and Web Endpoints
# =============================================================================

ASTOR_API_URL: Final[str] = "https://backend.premiumkino.de/v1/de/hannover/program"
"""Astor Grand Cinema API endpoint for movie program data."""

STAATSTHEATER_CALENDAR_URL: Final[str] = (
    "https://staatstheater-hannover.de/de_DE/kalender"
)
"""Staatstheater Hannover calendar page for HTML scraping."""


# =============================================================================
# Concert Venue Configuration
# =============================================================================


class VenueSelectors(TypedDict, total=False):
    """CSS selectors for extracting event data from venue pages."""

    container: str
    event: str
    title: str
    date: str
    location: str
    venue: str


class VenueConfig(TypedDict):
    """Configuration for a concert venue scraper."""

    name: str
    url: str
    enabled: bool
    selectors: VenueSelectors


CONCERT_VENUES: Final[tuple[VenueConfig, ...]] = (
    {
        "name": "ZAG Arena",
        "url": "https://www.zag-arena-hannover.de/veranstaltungen/",
        "enabled": True,
        "selectors": {
            "container": ".wpem-event-listings",
            "event": ".wpem-event-layout-wrapper",
            "title": ".wpem-heading-text a",
            "date": ".wpem-from-date",
            "location": ".wpem-event-infomation",
        },
    },
    {
        "name": "Swiss Life Hall",
        "url": "https://www.swisslife-hall.de/events/",
        "enabled": True,
        "selectors": {
            "event": "a.hc-card-link-wrapper",
            "title": "h4, h3",
            "date": ".hc-date-info",
            "venue": "Swiss Life Hall",
        },
    },
    {
        "name": "Capitol Hannover",
        "url": "https://www.capitol-hannover.de/events/",
        "enabled": True,
        "selectors": {
            "event": "a.hc-card-link-wrapper",
            "title": "h4, h3",
            "date": ".hc-date-info",
            "venue": "Capitol Hannover",
        },
    },
)
"""Concert venue configurations with CSS selectors for scraping."""


# =============================================================================
# Filtering Configuration
# =============================================================================

IGNORE_KEYWORDS: Final[tuple[str, ...]] = (
    "Führung",
    "Einführung",
    "Kindertheater",
    "Kindertanz",
    "Workshop",
    "Probe",
    "Geschlossene Veranstaltung",
)
"""Keywords to filter out unwanted events (tours, workshops, children's events)."""


# =============================================================================
# HTTP Client Settings
# =============================================================================

REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0
"""HTTP request timeout in seconds."""

USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
"""User-Agent header for HTTP requests."""


# =============================================================================
# Telegram Settings
# =============================================================================

TELEGRAM_MESSAGE_MAX_LENGTH: Final[int] = 4096
"""Maximum message length allowed by Telegram API."""


# =============================================================================
# German Month Name Mappings
# =============================================================================

GERMAN_MONTH_MAP: Final[dict[str, int]] = {
    "jan": 1,
    "januar": 1,
    "feb": 2,
    "februar": 2,
    "mär": 3,
    "märz": 3,
    "mar": 3,
    "apr": 4,
    "april": 4,
    "mai": 5,
    "may": 5,
    "jun": 6,
    "juni": 6,
    "jul": 7,
    "juli": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "okt": 10,
    "oktober": 10,
    "oct": 10,
    "nov": 11,
    "november": 11,
    "dez": 12,
    "dezember": 12,
    "dec": 12,
}
"""Mapping of German month names/abbreviations to month numbers."""
