"""Event aggregation from all registered sources.

This module provides the central orchestration for fetching events
from all registered sources and categorizing them for output.

Usage:
    from boringhannover.aggregator import fetch_all_events

    events = fetch_all_events()
    # Returns: {"movies_this_week": [...], "big_events_radar": [...], ...}
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import datetime
from typing import TYPE_CHECKING

from boringhannover.config import SCRAPE_DELAY_SECONDS
from boringhannover.constants import BERLIN_TZ, EVENT_LOOKAHEAD_DAYS
from boringhannover.source_outcomes import IncompleteDiscoveryError, SourceOutcome
from boringhannover.sources import get_all_sources
from boringhannover.sources.base import BaseSource


if TYPE_CHECKING:
    from collections.abc import Mapping

    from boringhannover.models import Event
    from boringhannover.occasions import OccasionDefinition
    from boringhannover.output import EventsData

__all__ = ["fetch_all_events"]

logger = logging.getLogger(__name__)


def fetch_all_events(
    sources: Mapping[str, type[BaseSource]] | None = None,
    *,
    now: datetime | None = None,
) -> EventsData:
    """Fetch and categorize events from all registered sources.

    Orchestrates all registered and enabled scrapers, then categorizes
    events into time-based buckets:
    - movies_this_week: Movie showtimes within the configured lookahead window
    - big_events_radar: Concerts/events within the configured lookahead window

    Both categories use the same 2-week window to keep the UI focused.

    Fetching and occasion discovery are separate operations: each records a
    SourceOutcome, and one failing does not skip the other. A source that
    only carries its own occasion definition discovers nothing, so it records
    no discovery outcome. Disabled sources record nothing.

    Args:
        sources: Sources to fetch from; defaults to every registered source.
        now: The clock both windows share; defaults to after fetching.

    Returns:
        Categorized event lists, every occasion read (including those from a
        partial discovery) and each operation's outcome.

    Example:
        >>> events = fetch_all_events()
        >>> print(f"Movies: {len(events['movies_this_week'])}")
        >>> print(f"Radar: {len(events['big_events_radar'])}")
    """
    logger.info("Fetching events from all registered sources...")

    all_movies: list[Event] = []
    radar_events: list[Event] = []
    city_occasions: list[OccasionDefinition] = []
    outcomes: list[SourceOutcome] = []

    if sources is None:
        sources = get_all_sources()
    logger.info("Found %d registered sources", len(sources))

    # Fetch from each enabled source with rate limiting
    source_count = 0
    for name, source_cls in sources.items():
        try:
            source = source_cls()
        except Exception as exc:
            logger.warning("Source %s failed: %s", name, exc)
            outcomes.append(SourceOutcome.failed(name, "fetch", exc))
            if _discovers_occasions(source_cls):
                outcomes.append(SourceOutcome.failed(name, "discover_occasions", exc))
            continue

        # Skip disabled sources
        if not source.enabled:
            logger.debug("Skipping disabled source: %s", name)
            continue

        # Delay between sources to avoid IP blocks
        if source_count > 0:
            logger.debug(
                "Rate limiting: waiting %.1fs before next source",
                SCRAPE_DELAY_SECONDS,
            )
            time.sleep(SCRAPE_DELAY_SECONDS)
        source_count += 1

        events, outcome = _fetch(name, source)
        outcomes.append(outcome)
        # Categorize events by type
        for event in events:
            if event.category == "movie":
                all_movies.append(event)
            else:
                radar_events.append(event)

        occasions, outcome = _discover_occasions(name, source)
        city_occasions.extend(occasions)
        if outcome is not None:
            outcomes.append(outcome)

    states = Counter(outcome.state for outcome in outcomes)
    logger.info(
        "Source outcomes: %s",
        ", ".join(f"{count} {state}" for state, count in sorted(states.items()))
        or "none",
    )

    now = now or datetime.now(BERLIN_TZ)
    # Filter movies to the configured lookahead window
    movies_this_week = sorted(
        (m for m in all_movies if m.is_within_next_days(EVENT_LOOKAHEAD_DAYS, now=now)),
        key=lambda e: e.date,
    )

    # Filter concerts to the same lookahead window as movies
    big_events_radar = sorted(
        (
            r
            for r in radar_events
            if r.is_within_next_days(EVENT_LOOKAHEAD_DAYS, now=now)
        ),
        key=lambda e: e.date,
    )

    logger.info(
        "Aggregation complete: %d movies, %d concerts (next %d days)",
        len(movies_this_week),
        len(big_events_radar),
        EVENT_LOOKAHEAD_DAYS,
    )

    return {
        "movies_this_week": movies_this_week,
        "big_events_radar": big_events_radar,
        "city_occasions": city_occasions,
        "source_outcomes": outcomes,
    }


def _fetch(name: str, source: BaseSource) -> tuple[list[Event], SourceOutcome]:
    """Fetch one source's events; a failure isolates to this source.

    No fetch adapter confirms it read its whole source, so completion stays
    unknown and an empty fetch is never proof that the source is empty.
    """
    logger.debug("Fetching from source: %s (%s)", name, source.source_name)
    try:
        events = source.fetch()
    except Exception as exc:
        logger.warning("Source %s failed: %s", name, exc)
        return [], SourceOutcome.failed(name, "fetch", exc)

    logger.info("Source %s: fetched %d events", source.source_name, len(events))
    return events, SourceOutcome.finished(
        name, "fetch", len(events), completion="unknown"
    )


def _discovers_occasions(source_cls: type[BaseSource]) -> bool:
    """Whether a source observes occasions rather than only carrying its own."""
    return source_cls.discover_occasions is not BaseSource.discover_occasions


def _discover_occasions(
    name: str,
    source: BaseSource,
) -> tuple[list[OccasionDefinition], SourceOutcome | None]:
    """Run one source's occasion discovery and record what it observed.

    The base implementation only returns the source's own definition, which
    is configuration rather than an observation, so it records no outcome.
    A discovering source returns its complete inventory or raises; a partial
    one keeps every occasion it read.
    """
    if not _discovers_occasions(type(source)):
        return source.discover_occasions(), None

    try:
        occasions = source.discover_occasions()
    except IncompleteDiscoveryError as exc:
        logger.warning(
            "Occasion discovery for source %s is incomplete: %s", name, exc.reason
        )
        return exc.occasions, SourceOutcome.partial(
            name, "discover_occasions", len(exc.occasions), exc.reason
        )
    except Exception as exc:
        logger.warning("Occasion discovery for source %s failed: %s", name, exc)
        return [], SourceOutcome.failed(name, "discover_occasions", exc)

    return occasions, SourceOutcome.finished(
        name, "discover_occasions", len(occasions), completion="complete"
    )
