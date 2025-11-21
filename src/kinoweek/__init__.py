"""KinoWeek - Weekly event aggregator for Hannover.

A stateless, weekly script that fetches cultural events from three sources
and delivers a formatted digest via Telegram:

1. Astor Grand Cinema - OV (Original Version) movies
2. Staatstheater Hannover - Opera, ballet, and theater
3. Concert Venues - Major concerts and big events

Usage:
    # Run in development mode (saves to local files)
    kinoweek --local

    # Run in production mode (sends to Telegram)
    kinoweek

Example:
    >>> from kinoweek.scrapers import fetch_all_events
    >>> from kinoweek.notifier import format_message
    >>>
    >>> events = fetch_all_events()
    >>> message = format_message(events)
    >>> print(message)
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "Sia"

__all__ = [
    # Version info
    "__version__",
    "__author__",
    # Main entry point
    "main",
    "run",
    # Models
    "Event",
    # Scrapers
    "fetch_all_events",
    "AstorMovieScraper",
    "StaatstheaterScraper",
    "ConcertVenueScraper",
    # Notifier
    "notify",
    "format_message",
]

# Lazy imports to avoid circular dependencies
def __getattr__(name: str):
    """Lazy import public API components."""
    if name in ("main", "run"):
        from kinoweek.main import main, run
        return main if name == "main" else run

    if name == "Event":
        from kinoweek.models import Event
        return Event

    if name == "fetch_all_events":
        from kinoweek.scrapers import fetch_all_events
        return fetch_all_events

    if name in ("AstorMovieScraper", "StaatstheaterScraper", "ConcertVenueScraper"):
        from kinoweek import scrapers
        return getattr(scrapers, name)

    if name in ("notify", "format_message"):
        from kinoweek import notifier
        return getattr(notifier, name)

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
