"""KinoWeek - Weekly event aggregator for Hannover.

A stateless, weekly script that fetches cultural events from multiple sources
and delivers a formatted digest via Telegram:

1. Astor Grand Cinema - OV (Original Version) movies
2. Concert Venues - Major concerts and big events (ZAG Arena, Swiss Life Hall, Capitol)

Outputs multiple formats:
- Telegram message (Markdown)
- CSV files (movies.csv, movies_grouped.csv, concerts.csv)
- Enhanced JSON (events.json)
- Markdown digest (weekly_digest.md)
- Weekly archive (archive/YYYY-WXX.json)

Usage:
    # Run in development mode (saves to local files)
    kinoweek --local

    # Run in production mode (sends to Telegram)
    kinoweek

Example:
    >>> from kinoweek.scrapers import fetch_all_events
    >>> from kinoweek.notifier import format_message
    >>> from kinoweek.output import export_all_formats
    >>>
    >>> events = fetch_all_events()
    >>> message = format_message(events)
    >>> export_all_formats(events["movies_this_week"], events["big_events_radar"])
"""

from __future__ import annotations

__version__ = "0.2.0"
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
    "ConcertVenueScraper",
    # Notifier
    "notify",
    "format_message",
    # Output
    "OutputManager",
    "export_all_formats",
    "group_movies_by_film",
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

    if name in ("AstorMovieScraper", "ConcertVenueScraper"):
        from kinoweek import scrapers
        return getattr(scrapers, name)

    if name in ("notify", "format_message"):
        from kinoweek import notifier
        return getattr(notifier, name)

    if name in ("OutputManager", "export_all_formats", "group_movies_by_film"):
        from kinoweek import output
        return getattr(output, name)

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
