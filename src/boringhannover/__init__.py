"""BoringHannover - Weekly event aggregator for Hannover.

A modular, stateless script that fetches cultural events from multiple sources
and exports data in multiple formats.

Architecture:
- sources/: Plugin-based source modules (auto-discovered)
  - cinema/: Movie theater sources (Astor)
  - concerts/: Concert venue sources (ZAG Arena, Swiss Life Hall, Capitol)
- aggregator.py: Central orchestration for all sources
- notifier.py: Message formatting and file output
- output.py: Multi-format export (CSV, JSON, Markdown)
- github_sync.py: Syncs data to repo to trigger frontend rebuild

Outputs multiple formats:
- CSV files (movies.csv, movies_grouped.csv, concerts.csv)
- Enhanced JSON (events.json, web_events.json)
- Markdown digest (weekly_digest.md)
- Weekly archive (archive/YYYY-WXX.json)

Usage:
    # Run the scraper
    boringhannover

Example:
    >>> from boringhannover.aggregator import fetch_all_events
    >>> from boringhannover.notifier import format_message
    >>> from boringhannover.output import export_all_formats
    >>>
    >>> events = fetch_all_events()
    >>> message = format_message(events)
    >>> export_all_formats(events["movies_this_week"], events["big_events_radar"])

Adding a new source:
    1. Create a module in sources/cinema/ or sources/concerts/
    2. Import BaseSource and register_source from boringhannover.sources
    3. Decorate your class with @register_source("unique_name")
    4. The source is auto-discovered on import
"""

from __future__ import annotations


__version__ = "0.3.0"
__author__ = "Sia"

__all__ = [  # noqa: RUF022
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
def __getattr__(name: str):  # type: ignore[no-untyped-def]  # noqa: PLR0911
    """Lazy import public API components."""
    if name in ("main", "run"):
        from boringhannover.main import main, run  # noqa: PLC0415

        return main if name == "main" else run

    if name == "Event":
        from boringhannover.models import Event  # noqa: PLC0415

        return Event

    if name == "fetch_all_events":
        from boringhannover.aggregator import fetch_all_events  # noqa: PLC0415

        return fetch_all_events

    # New source architecture exports
    if name in (
        "BaseSource",
        "register_source",
        "get_all_sources",
        "get_sources_by_type",
    ):
        from boringhannover import sources  # noqa: PLC0415

        return getattr(sources, name)

    # Backward compatibility: old scraper classes
    # These are deprecated but still exported for compatibility
    if name == "AstorMovieScraper":
        from boringhannover.sources.cinema.astor import AstorSource  # noqa: PLC0415

        return AstorSource

    if name == "ConcertVenueScraper":
        # Return ZAGArenaSource as a compatibility alias
        from boringhannover.sources.concerts.zag_arena import (  # noqa: PLC0415
            ZAGArenaSource,
        )

        return ZAGArenaSource

    if name in ("notify", "format_message"):
        from boringhannover import notifier  # noqa: PLC0415

        return getattr(notifier, name)

    if name in ("OutputManager", "export_all_formats", "group_movies_by_film"):
        from boringhannover import output  # noqa: PLC0415

        return getattr(output, name)

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
