"""Helpers for event start-time confidence.

Scrapers sometimes need a fallback datetime to sort date-only listings. That
fallback must not be displayed as a real event start time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from boringhannover.constants import BERLIN_TZ


if TYPE_CHECKING:
    from datetime import datetime

    from boringhannover.models import Event

CONFIRMED_TIME: Final[str] = "confirmed"
FALLBACK_TIME: Final[str] = "fallback"


def has_started(start: datetime, now: datetime, *, fallback_time: bool) -> bool:
    """Whether an event has started, for listing purposes.

    A fallback time only sorts a date-only event, so that event stays listed
    for its whole Berlin day; a confirmed time counts from the minute itself.
    """
    if fallback_time:
        return start.astimezone(BERLIN_TZ).date() < now.astimezone(BERLIN_TZ).date()
    return start < now


def get_display_time(event: Event) -> str | None:
    """Return event time only when the source provided a confirmed time."""
    if event.metadata.get("time_confidence") == FALLBACK_TIME:
        return None

    raw_time = event.metadata.get("time")
    if not raw_time:
        return None

    return str(raw_time)


def get_time_confidence(event: Event) -> str:
    """Return normalized confidence for an event time."""
    raw_confidence = event.metadata.get("time_confidence")
    if raw_confidence in {CONFIRMED_TIME, FALLBACK_TIME}:
        return str(raw_confidence)
    return CONFIRMED_TIME if event.metadata.get("time") else FALLBACK_TIME
