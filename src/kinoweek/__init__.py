"""KinoWeek - Weekly event aggregator for Hannover.

A modular, stateless script that fetches cultural events from multiple sources
and delivers a formatted digest via Telegram.

Architecture:
- sources/: Plugin-based source modules (auto-discovered)
  - cinema/: Movie theater sources (Astor)
  - concerts/: Concert venue sources (ZAG Arena, Swiss Life Hall, Capitol)
- aggregator.py: Central orchestration for all sources
- notifier.py: Telegram notification and file output
- output.py: Multi-format export (CSV, JSON, Markdown)

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
    >>> from kinoweek.aggregator import fetch_all_events
    >>> from kinoweek.notifier import format_message
    >>> from kinoweek.output import export_all_formats
    >>>
    >>> events = fetch_all_events()
    >>> message = format_message(events)
    >>> export_all_formats(events["movies_this_week"], events["big_events_radar"])

Adding a new source:
    1. Create a module in sources/cinema/ or sources/concerts/
    2. Import BaseSource and register_source from kinoweek.sources
    3. Decorate your class with @register_source("unique_name")
    4. The source is auto-discovered on import
"""

from __future__ import annotations

__version__ = "0.3.0"
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
    # Aggregator (new architecture)
    "fetch_all_events",
    # Sources (new architecture)
    "BaseSource",
    "register_source",
    "get_all_sources",
    "get_sources_by_type",
    # Backward compatibility (old scrapers)
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
        from kinoweek.aggregator import fetch_all_events

        return fetch_all_events

    # New source architecture exports
    if name in ("BaseSource", "register_source", "get_all_sources", "get_sources_by_type"):
        from kinoweek import sources

        return getattr(sources, name)

    # Backward compatibility: old scraper classes
    # These are deprecated but still exported for compatibility
    if name == "AstorMovieScraper":
        from kinoweek.sources.cinema.astor import AstorSource

        return AstorSource

    if name == "ConcertVenueScraper":
        # Return a compatibility wrapper or the old class
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
