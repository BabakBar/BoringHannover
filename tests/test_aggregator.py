"""Aggregation keeps events in whole Berlin calendar days, read as Berlin time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from boringhannover.aggregator import fetch_all_events
from boringhannover.constants import BERLIN_TZ, EVENT_LOOKAHEAD_DAYS
from boringhannover.event_time import CONFIRMED_TIME, FALLBACK_TIME
from boringhannover.models import Event
from boringhannover.occasions import OccasionDefinition, occasion_lifecycle
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


def berlin(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=BERLIN_TZ)


# Day 14 of each clock is a hard case: the autumn and spring clock changes,
# and a horizon that crosses New Year. ``inside`` is in chronological order.
@pytest.mark.parametrize(
    ("now", "inside", "outside"),
    [
        pytest.param(
            berlin(2026, 10, 11, 9, 0),
            [
                berlin(2026, 10, 11, 20, 0),
                datetime(2026, 10, 25, 0, 30),  # noqa: DTZ001 - naive is Berlin
                datetime(2026, 10, 25, 22, 30, tzinfo=UTC),  # 23:30 in Berlin
            ],
            [
                berlin(2026, 10, 11, 8, 0),  # already started
                datetime(2026, 10, 25, 23, 30, tzinfo=UTC),  # 00:30 on day 15
                datetime(2026, 10, 26, 0, 0),  # noqa: DTZ001
            ],
            id="autumn-clock-change-on-day-14",
        ),
        pytest.param(
            berlin(2026, 3, 15, 23, 0),
            [berlin(2026, 3, 15, 23, 30), berlin(2026, 3, 29, 23, 59)],
            [berlin(2026, 3, 30, 0, 0)],
            id="spring-clock-change-on-day-14",
        ),
        pytest.param(
            berlin(2026, 12, 21, 12, 0),
            [berlin(2027, 1, 4, 23, 0)],
            [berlin(2026, 12, 21, 11, 59), berlin(2027, 1, 5, 0, 0)],
            id="year-rollover",
        ),
    ],
)
def test_window_runs_through_the_end_of_berlin_day_14(
    now: datetime, inside: list[datetime], outside: list[datetime]
) -> None:
    """Movies and Radar keep today..today+14 inclusive, like City Occasions."""

    class StaticSource(BaseSource):
        source_name = "Static"
        source_type = "cinema"

        def fetch(self) -> list[Event]:
            return [
                Event(
                    title=f"{category} {when.isoformat()}",
                    date=when,
                    venue="Venue",
                    url="https://example.com",
                    category=category,
                )
                for when in [*outside, *inside]
                for category in ("movie", "radar")
            ]

    result = fetch_all_events(sources={"static": StaticSource}, now=now)

    assert [event.title for event in result["movies_this_week"]] == [
        f"movie {when.isoformat()}" for when in inside
    ]
    assert [event.title for event in result["big_events_radar"]] == [
        f"radar {when.isoformat()}" for when in inside
    ]

    # The same clock lists a one-day occasion on day 14, not one on day 15.
    def one_day_occasion(offset: int) -> OccasionDefinition:
        day = now.date() + timedelta(days=offset)
        return OccasionDefinition(
            id=f"test:{day}",
            slug=f"test-{day}",
            name="Fest",
            kind="festival",
            start_date=day,
            end_date=day,
            location="Venue",
            source_url="https://example.com",
            description="",
        )

    last = inside[-1]
    last_day = (
        last.astimezone(BERLIN_TZ) if last.tzinfo else last.replace(tzinfo=BERLIN_TZ)
    ).date()
    assert last_day == now.date() + timedelta(days=EVENT_LOOKAHEAD_DAYS)
    assert occasion_lifecycle(one_day_occasion(EVENT_LOOKAHEAD_DAYS), now) is not None
    assert occasion_lifecycle(one_day_occasion(EVENT_LOOKAHEAD_DAYS + 1), now) is None


def test_date_only_events_stay_listed_for_their_whole_berlin_day() -> None:
    """A fallback time is a placeholder, so it never expires an event early."""
    now = berlin(2026, 10, 11, 20, 1)  # the Sunday-evening scrape

    class StaticSource(BaseSource):
        source_name = "Static"
        source_type = "concert"

        def fetch(self) -> list[Event]:
            return [
                Event(
                    title=title,
                    date=when,
                    venue="Venue",
                    url="https://example.com",
                    category="radar",
                    metadata={"time_confidence": confidence},
                )
                for title, when, confidence in [
                    ("all day", berlin(2026, 10, 11, 12, 0), FALLBACK_TIME),
                    ("date only", berlin(2026, 10, 11, 20, 0), FALLBACK_TIME),
                    ("started", berlin(2026, 10, 11, 20, 0), CONFIRMED_TIME),
                    ("yesterday", berlin(2026, 10, 10, 20, 0), FALLBACK_TIME),
                    ("day 14", berlin(2026, 10, 25, 20, 0), FALLBACK_TIME),
                    ("day 15", berlin(2026, 10, 26, 20, 0), FALLBACK_TIME),
                ]
            ]

    result = fetch_all_events(sources={"static": StaticSource}, now=now)

    assert [event.title for event in result["big_events_radar"]] == [
        "all day",
        "date only",
        "day 14",
    ]


def test_fetch_and_discovery_outcomes_stay_distinct() -> None:
    """A failed fetch neither skips discovery nor is hidden by its success,
    and configuration is never recorded as an observation."""
    now = berlin(2026, 10, 15, 9, 0)
    fest = OccasionDefinition(
        id="test:fest",
        slug="fest",
        name="Fest",
        kind="festival",
        start_date=now.date(),
        end_date=now.date(),
        location="Venue",
        source_url="https://example.com",
        description="",
    )

    class BrokenVenue(BaseSource):
        source_name = "Broken"
        source_type = "concert"

        def fetch(self) -> list[Event]:
            msg = "venue moved"
            raise ConnectionError(msg)

        def discover_occasions(self) -> list[OccasionDefinition]:
            return [fest]

    class OwnOccasion(BaseSource):
        source_name = "Own"
        source_type = "festival"
        occasion = fest

        def fetch(self) -> list[Event]:
            return []

    class Disabled(OwnOccasion):
        enabled = False

    class Unbuildable(BrokenVenue):
        def __init__(self) -> None:
            msg = "bad config"
            raise ValueError(msg)

    result = fetch_all_events(
        sources={
            "broken": BrokenVenue,
            "own": OwnOccasion,
            "off": Disabled,
            "unbuildable": Unbuildable,
        },
        now=now,
    )

    assert [str(outcome) for outcome in result["source_outcomes"]] == [
        "broken fetch: failed, 0 usable, completion incomplete "
        "(ConnectionError: venue moved)",
        "broken discover_occasions: success, 1 usable, completion complete",
        "own fetch: empty, 0 usable, completion unknown",
        # Discovery that never ran is a failure, not a missing observation.
        "unbuildable fetch: failed, 0 usable, completion incomplete "
        "(ValueError: bad config)",
        "unbuildable discover_occasions: failed, 0 usable, completion incomplete "
        "(ValueError: bad config)",
    ]
    assert result.get("city_occasions") == [fest, fest]
