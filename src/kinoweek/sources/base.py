"""Base classes and registry for KinoWeek event sources.

This module provides:
- BaseSource: Abstract base class for all event sources
- @register_source: Decorator for automatic source registration
- Registry functions: get_source, get_all_sources, get_sources_by_type

Example:
    @register_source("my_venue")
    class MyVenueSource(BaseSource):
        source_name = "My Venue"
        source_type = "concert"

        def fetch(self) -> list[Event]:
            ...
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Callable, ClassVar, Final, TypeVar

import httpx

from kinoweek.config import (
    GERMAN_MONTH_MAP,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
)

if TYPE_CHECKING:
    from kinoweek.models import Event

__all__ = [
    "BaseSource",
    "register_source",
    "get_source",
    "get_all_sources",
    "get_sources_by_type",
    "create_http_client",
    "parse_german_date",
    "parse_venue_date",
    "is_original_version",
]

logger = logging.getLogger(__name__)

# =============================================================================
# Source Registry
# =============================================================================

_REGISTRY: dict[str, type[BaseSource]] = {}

T = TypeVar("T", bound="BaseSource")


def register_source(name: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register a source in the global registry.

    Args:
        name: Unique identifier for the source (e.g., "astor_hannover").

    Returns:
        Decorator function that registers the class.

    Example:
        @register_source("my_cinema")
        class MyCinemaSource(BaseSource):
            ...
    """

    def decorator(cls: type[T]) -> type[T]:
        if name in _REGISTRY:
            logger.warning(
                "Source '%s' already registered, overwriting with %s",
                name,
                cls.__name__,
            )
        _REGISTRY[name] = cls
        logger.debug("Registered source: %s -> %s", name, cls.__name__)
        return cls

    return decorator


def get_source(name: str) -> type[BaseSource]:
    """Get a source class by its registered name.

    Args:
        name: The registered source name.

    Returns:
        The source class.

    Raises:
        KeyError: If source is not found.
    """
    if name not in _REGISTRY:
        available = ", ".join(_REGISTRY.keys())
        raise KeyError(f"Source '{name}' not found. Available: {available}")
    return _REGISTRY[name]


def get_all_sources() -> dict[str, type[BaseSource]]:
    """Get all registered sources.

    Returns:
        Dictionary mapping source names to source classes.
    """
    return _REGISTRY.copy()


def get_sources_by_type(source_type: str) -> dict[str, type[BaseSource]]:
    """Get all sources of a specific type.

    Args:
        source_type: Type to filter by (e.g., "cinema", "concert").

    Returns:
        Dictionary of matching sources.
    """
    return {
        name: cls
        for name, cls in _REGISTRY.items()
        if cls.source_type == source_type
    }


# =============================================================================
# Base Source Class
# =============================================================================


class BaseSource(ABC):
    """Abstract base class for all event sources.

    Subclasses must implement:
    - source_name: Human-readable name (e.g., "Astor Grand Cinema")
    - source_type: Category (e.g., "cinema", "concert", "theater")
    - fetch(): Method to retrieve events

    Optional overrides:
    - enabled: Whether the source is active (default: True)
    - max_events: Maximum events to fetch (default: None = unlimited)

    Class Attributes:
        source_name: Human-readable source name.
        source_type: Source category for grouping.
        enabled: Whether this source is active.
        max_events: Optional limit on events to fetch.
    """

    # Subclasses must define these
    source_name: ClassVar[str]
    source_type: ClassVar[str]

    # Optional configuration
    enabled: ClassVar[bool] = True
    max_events: ClassVar[int | None] = None

    @abstractmethod
    def fetch(self) -> list[Event]:
        """Fetch events from this source.

        Returns:
            List of Event objects from this source.

        Raises:
            httpx.RequestError: If the HTTP request fails.
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.source_name!r}, type={self.source_type!r})>"


# =============================================================================
# Shared Helper Functions
# =============================================================================


def create_http_client() -> httpx.Client:
    """Create a configured HTTP client with standard headers.

    Returns:
        Configured httpx.Client instance.
    """
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )


def is_original_version(language: str) -> bool:
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


def parse_german_date(date_str: str) -> datetime | None:
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


def parse_venue_date(date_str: str) -> datetime | None:
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
