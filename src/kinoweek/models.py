"""
Simple data models for KinoWeek events.

This module defines the core Event dataclass used across all scrapers.
No database needed - this is a stateless, weekly script.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    """
    Unified event structure for all sources (movies, culture, concerts).

    Attributes:
        title: Event title/name
        date: Event date and time
        venue: Venue name
        url: Link to event details
        category: Event type - "movie", "culture", or "radar"
        metadata: Optional additional info (duration, FSK, language, etc.)
    """
    title: str
    date: datetime
    venue: str
    url: str
    category: str  # "movie", "culture", "radar"
    metadata: Optional[dict] = None

    def __post_init__(self):
        """Validate category and initialize metadata if None."""
        valid_categories = {"movie", "culture", "radar"}
        if self.category not in valid_categories:
            raise ValueError(
                f"Invalid category '{self.category}'. "
                f"Must be one of {valid_categories}"
            )

        if self.metadata is None:
            self.metadata = {}

    def format_date_short(self) -> str:
        """Format date as 'Mon 24.11.'"""
        return self.date.strftime("%a %d.%m.")

    def format_date_long(self) -> str:
        """Format date as '12. Dec' or '15. Mar 2026'"""
        # Include year if not current year
        today = datetime.now()
        if self.date.year != today.year:
            return self.date.strftime("%d. %b %Y")
        return self.date.strftime("%d. %b")

    def format_time(self) -> str:
        """Format time as 'Fri 19:30'"""
        return self.date.strftime("%a %H:%M")

    def is_this_week(self) -> bool:
        """Check if event is within the next 7 days."""
        from datetime import timedelta
        today = datetime.now()
        next_week = today + timedelta(days=7)
        return today <= self.date <= next_week
