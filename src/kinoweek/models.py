"""Data models for KinoWeek events.

This module defines the core Event dataclass used across all scrapers.
Uses modern Python 3.13+ features for type safety and performance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from typing import Self

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
    """

    title: str
    date: datetime
    venue: str
    url: str
    category: EventCategory
    metadata: EventMetadata = field(default_factory=dict)

    def format_date_short(self) -> str:
        """Format date as weekday and date (e.g., 'Mon 24.11.').

        Returns:
            Formatted date string with weekday abbreviation.
        """
        return self.date.strftime("%a %d.%m.")

    def format_date_long(self) -> str:
        """Format date with month name and optional year.

        Includes year only if the event is not in the current year.

        Returns:
            Formatted date like '12. Dec' or '15. Mar 2026'.
        """
        today = datetime.now()
        if self.date.year != today.year:
            return self.date.strftime("%d. %b %Y")
        return self.date.strftime("%d. %b")

    def format_time(self) -> str:
        """Format as weekday and time (e.g., 'Fri 19:30').

        Returns:
            Formatted time string with weekday abbreviation.
        """
        return self.date.strftime("%a %H:%M")

    def is_this_week(self) -> bool:
        """Check if event occurs within the next 7 days.

        Returns:
            True if event date is between now and 7 days from now.
        """
        today = datetime.now()
        next_week = today + timedelta(days=7)
        return today <= self.date <= next_week
