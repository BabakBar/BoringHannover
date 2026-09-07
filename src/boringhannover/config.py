"""Configuration settings for BoringHannover scrapers.

All URLs, selectors, and settings are centralized here for easy maintenance.
Uses Final for immutable constants.
"""

from __future__ import annotations

from typing import Final


__all__ = [
    "ASTOR_API_URL",
    "GERMAN_MONTH_MAP",
    "REQUEST_TIMEOUT_SECONDS",
    "SCRAPE_DELAY_SECONDS",
    "USER_AGENT",
]


# =============================================================================
# API and Web Endpoints
# =============================================================================

ASTOR_API_URL: Final[str] = "https://backend.premiumkino.de/v1/de/hannover/program"
"""Astor Grand Cinema API endpoint for movie program data."""


# =============================================================================
# HTTP Client Settings
# =============================================================================

REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0
"""HTTP request timeout in seconds."""

# BS-4: Rate limiting configuration
SCRAPE_DELAY_SECONDS: Final[float] = 1.0
"""Delay between scraping different sources to avoid IP blocks."""

USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
"""User-Agent header for HTTP requests."""


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
