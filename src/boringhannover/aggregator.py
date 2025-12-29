"""Event aggregation from all registered sources.

This module provides the central orchestration for fetching events
from all registered sources and categorizing them for output.

Usage:
    from boringhannover.aggregator import fetch_all_events

    events = fetch_all_events()
    # Returns: {"movies_this_week": [...], "big_events_radar": [...]}
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING

from boringhannover.config import SCRAPE_DELAY_SECONDS
from boringhannover.constants import BERLIN_TZ, MOVIES_LOOKAHEAD_DAYS
from boringhannover.sources import get_all_sources


if TYPE_CHECKING:
    from boringhannover.models import Event

__all__ = ["fetch_all_events"]

logger = logging.getLogger(__name__)


def fetch_all_events() -> dict[str, list[Event]]:
    """Fetch and categorize events from all registered sources.

    Orchestrates all registered and enabled scrapers, then categorizes
    events into time-based buckets:
    - movies_this_week: Movie showtimes within the configured lookahead window
    - big_events_radar: All concerts/events from today onward

    Returns:
        Dictionary with categorized event lists.

    Example:
        >>> events = fetch_all_events()
        >>> print(f"Movies: {len(events['movies_this_week'])}")
        >>> print(f"Radar: {len(events['big_events_radar'])}")
    """
    today = datetime.now(BERLIN_TZ)

    logger.info("Fetching events from all registered sources...")

    all_movies: list[Event] = []
    radar_events: list[Event] = []

    # Get all registered sources
    sources = get_all_sources()
    logger.info("Found %d registered sources", len(sources))

    # Fetch from each enabled source with rate limiting (BS-4)
    source_count = 0
    for name, source_cls in sources.items():
        try:
            source = source_cls()

            # Skip disabled sources
            if not source.enabled:
                logger.debug("Skipping disabled source: %s", name)
                continue

            # BS-4: Add delay between sources to avoid IP blocks
            if source_count > 0:
                logger.debug(
                    "Rate limiting: waiting %.1fs before next source",
                    SCRAPE_DELAY_SECONDS,
                )
                time.sleep(SCRAPE_DELAY_SECONDS)

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
            source_count += 1

        except Exception as exc:
            logger.warning("Source %s failed: %s", name, exc)
            # Continue with other sources - graceful degradation
            source_count += 1  # Still count failed sources for rate limiting

    # Filter movies to the configured lookahead window
    movies_this_week = sorted(
        (m for m in all_movies if m.is_within_next_days(MOVIES_LOOKAHEAD_DAYS)),
        key=lambda e: e.date,
    )

    # Include all concerts from today onward
    big_events_radar = sorted(
        (r for r in radar_events if r.date >= today),
        key=lambda e: e.date,
    )

    logger.info(
        "Aggregation complete: %d movies (next %d days), %d events on radar",
        len(movies_this_week),
        MOVIES_LOOKAHEAD_DAYS,
        len(big_events_radar),
    )

    return {
        "movies_this_week": movies_this_week,
        "big_events_radar": big_events_radar,
    }
