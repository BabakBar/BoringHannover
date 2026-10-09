"""Data models for BoringHannover events.

This module defines the core Event dataclass used across all scrapers.
Uses modern Python 3.13+ features for type safety and performance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from boringhannover.constants import BERLIN_TZ


__all__ = ["Event", "EventCategory", "EventMetadata"]

# Type aliases for clarity
EventCategory = Literal["movie", "culture", "radar"]
EventMetadata = dict[str, str | int | list[str]]


@dataclass(slots=True, kw_only=True)
class Event:
    """Unified event structure for all sources.

    Represents events from various sources (movies, culture, concerts)
    with a consistent interface for categorization and formatting.

    Attributes:
        title: Event title or name.
        date: Event date and time.
        venue: Venue name where the event takes place.
        url: Link to event details or tickets.
        category: Event type - must be "movie", "culture", or "radar".
        metadata: Additional info like duration, rating, language, etc.

    Example:
        >>> event = Event(
        ...     title="Inception",
        ...     date=datetime.now(),
        ...     venue="Astor Grand Cinema",
        ...     url="https://example.com",
        ...     category="movie",
        ...     metadata={"duration": 148, "rating": 12},
        ... )

    Raises:
        ValueError: If validation fails (title too long/empty, invalid URL scheme).
    """

    title: str
    date: datetime
    venue: str
    url: str
    category: EventCategory
    metadata: EventMetadata = field(default_factory=dict)

    # Validation limits (BS-2: Circuit breaker for bad scraper data)
    _MAX_TITLE_LENGTH: int = field(default=200, init=False, repr=False)
    _MAX_VENUE_LENGTH: int = field(default=100, init=False, repr=False)
    _MAX_URL_LENGTH: int = field(default=500, init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate event data to prevent garbage from corrupted sources.

        This acts as a circuit breaker - if a source website changes
        structure and scrapers grab garbage data, validation will fail
        fast rather than propagating bad data to the frontend.
        """
        # Normalize datetimes to Berlin timezone (some sources emit offset-naive datetimes).
        if not isinstance(self.date, datetime):
            msg = f"Event date must be a datetime, got {type(self.date)!r}"
            raise TypeError(msg)
        if self.date.tzinfo is None or self.date.tzinfo.utcoffset(self.date) is None:
            self.date = self.date.replace(tzinfo=BERLIN_TZ)
        else:
            self.date = self.date.astimezone(BERLIN_TZ)

        # Title validation
        if not self.title or not self.title.strip():
            msg = "Event title cannot be empty"
            raise ValueError(msg)
        if len(self.title) > self._MAX_TITLE_LENGTH:
            msg = f"Title too long ({len(self.title)} chars > {self._MAX_TITLE_LENGTH}) - possible scraper error"
            raise ValueError(msg)

        # Venue validation
        if len(self.venue) > self._MAX_VENUE_LENGTH:
            msg = f"Venue name too long ({len(self.venue)} chars > {self._MAX_VENUE_LENGTH})"
            raise ValueError(msg)

        # URL validation
        if self.url:
            if len(self.url) > self._MAX_URL_LENGTH:
                msg = f"URL too long ({len(self.url)} chars > {self._MAX_URL_LENGTH})"
                raise ValueError(msg)
            if not self.url.startswith(("http://", "https://")):
                msg = f"Invalid URL scheme: {self.url[:50]}"
                raise ValueError(msg)

    def is_within_next_days(self, days: int) -> bool:
        """Check if event occurs within the next N days (inclusive).

        Args:
            days: Lookahead window in days.

        Returns:
            True if event date is between now and now + days.
        """
        if days < 0:
            return False

        today = datetime.now(BERLIN_TZ)
        cutoff = today + timedelta(days=days)
        return today <= self.date <= cutoff
