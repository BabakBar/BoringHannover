"""Event aggregation from all registered sources.

This module provides the central orchestration for fetching events
from all registered sources and categorizing them for output.

Usage:
    from kinoweek.aggregator import fetch_all_events

    events = fetch_all_events()
    # Returns: {"movies_this_week": [...], "big_events_radar": [...]}
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from kinoweek.sources import get_all_sources

if TYPE_CHECKING:
    from kinoweek.models import Event

__all__ = [
    "fetch_all_events",
    "get_all_events",  # Backward compatibility alias
]

logger = logging.getLogger(__name__)


def fetch_all_events() -> dict[str, list[Event]]:
    """Fetch and categorize events from all registered sources.

    Orchestrates all registered and enabled scrapers, then categorizes
    events into time-based buckets:
    - movies_this_week: Movie showtimes within the next 7 days
    - big_events_radar: Concerts/events beyond 7 days (future planning)

    Returns:
        Dictionary with categorized event lists.

    Example:
        >>> events = fetch_all_events()
        >>> print(f"Movies: {len(events['movies_this_week'])}")
        >>> print(f"Radar: {len(events['big_events_radar'])}")
    """
    today = datetime.now()
    next_week = today + timedelta(days=7)

    logger.info("Fetching events from all registered sources...")

    all_movies: list[Event] = []
    radar_events: list[Event] = []

    # Get all registered sources
    sources = get_all_sources()
    logger.info("Found %d registered sources", len(sources))

    # Fetch from each enabled source
    for name, source_cls in sources.items():
        try:
            source = source_cls()

            # Skip disabled sources
            if not source.enabled:
                logger.debug("Skipping disabled source: %s", name)
                continue

            logger.debug("Fetching from source: %s (%s)", name, source.source_name)
            events = source.fetch()

            # Categorize events by type
            for event in events:
                if event.category == "movie":
                    all_movies.append(event)
                else:
                    radar_events.append(event)

            logger.info(
                "Source %s: fetched %d events",
                source.source_name,
                len(events),
            )

        except Exception as exc:
            logger.warning("Source %s failed: %s", name, exc)
            # Continue with other sources - graceful degradation

    # Filter movies to this week only
    movies_this_week = sorted(
        (m for m in all_movies if m.is_this_week()),
        key=lambda e: e.date,
    )

    # Filter radar to EXCLUDE this week (future events only)
    big_events_radar = sorted(
        (r for r in radar_events if r.date > next_week),
        key=lambda e: e.date,
    )

    logger.info(
        "Aggregation complete: %d movies this week, %d events on radar",
        len(movies_this_week),
        len(big_events_radar),
    )

    return {
        "movies_this_week": movies_this_week,
        "big_events_radar": big_events_radar,
    }


# Backward compatibility alias
get_all_events = fetch_all_events
