"""Sources may emit naive datetimes; they are read as Berlin local time."""

from __future__ import annotations

from datetime import datetime, timedelta

from boringhannover.aggregator import fetch_all_events
from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sources.base import BaseSource


def test_event_normalizes_naive_datetime_to_berlin_tz() -> None:
    """Naive datetimes are treated as Europe/Berlin."""
    naive = datetime(2025, 12, 12, 19, 30)  # noqa: DTZ001
    event = Event(
        title="Naive Date",
        date=naive,
        venue="Venue",
        url="https://example.com",
        category="movie",
    )
    assert event.date.tzinfo is BERLIN_TZ
    assert (event.date.hour, event.date.minute) == (19, 30)


def test_handles_naive_datetimes_from_sources() -> None:
    """Sources may emit naive datetimes; aggregation should not crash."""
    today = datetime.now(BERLIN_TZ)

    class StaticSource(BaseSource):
        source_name = "Static"
        source_type = "cinema"

        def fetch(self) -> list[Event]:
            return [
                Event(
                    title="Movie",
                    date=(today + timedelta(days=1)).replace(tzinfo=None),
                    venue="Venue",
                    url="https://example.com",
                    category="movie",
                ),
                Event(
                    title="Concert",
                    date=(today + timedelta(days=8)).replace(tzinfo=None),
                    venue="Venue",
                    url="https://example.com",
                    category="radar",
                ),
            ]

    result = fetch_all_events(sources={"static": StaticSource})

    assert [e.title for e in result["movies_this_week"]] == ["Movie"]
    assert [e.title for e in result["big_events_radar"]] == ["Concert"]
