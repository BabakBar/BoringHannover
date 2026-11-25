"""A run must observe every critical occasion discovery before it may publish (#137).

A discovery adapter that never runs (its module failed to import, or it was
never registered) leaves no outcome at all. Without an expected set, the
publication gate cannot tell that apart from a calendar with nothing on.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from boringhannover import aggregator, sources
from boringhannover.aggregator import fetch_all_events
from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.source_outcomes import (
    CRITICAL_DISCOVERY,
    SourceOutcome,
    publication_refusal,
)
from boringhannover.sources.base import BaseSource


if TYPE_CHECKING:
    from boringhannover.occasions import OccasionDefinition


NOW = datetime(2026, 11, 24, 12, 0, tzinfo=BERLIN_TZ)


class Venue(BaseSource):
    """A healthy venue, so the run always has something to publish."""

    source_name = "Venue"
    source_type = "concert"

    def fetch(self) -> list[Event]:
        return [
            Event(
                title="Concert",
                date=NOW + timedelta(days=1),
                venue="Venue",
                url="https://example.com/concert",
                category="radar",
            )
        ]


class Calendar(BaseSource):
    """Stands in for a critical calendar that read its listing and found nothing."""

    source_name = "Calendar"
    source_type = "festival"

    def fetch(self) -> list[Event]:
        return []

    def discover_occasions(self) -> list[OccasionDefinition]:
        return []


class SwitchedOff(Calendar):
    enabled = False


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(aggregator, "SCRAPE_DELAY_SECONDS", 0)


def test_production_expects_both_hannover_calendars() -> None:
    assert (
        frozenset({"hannover_festival_calendar", "hannover_christmas_calendar"})
        == CRITICAL_DISCOVERY
    )
    assert sources.get_all_sources().keys() >= CRITICAL_DISCOVERY


def test_every_critical_calendar_observed_publishes() -> None:
    result = fetch_all_events(
        sources={"venue": Venue} | dict.fromkeys(CRITICAL_DISCOVERY, Calendar),
        now=NOW,
    )
    # A complete empty discovery is an observation, and publishable.
    assert publication_refusal(result) is None


def test_a_removed_critical_calendar_refuses_publication() -> None:
    result = fetch_all_events(
        sources={"venue": Venue, "hannover_festival_calendar": Calendar},
        now=NOW,
    )
    assert publication_refusal(result) == (
        "missing critical occasion discovery: hannover_christmas_calendar"
    )


def test_a_disabled_critical_calendar_publishes_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    result = fetch_all_events(
        sources={
            "venue": Venue,
            "hannover_festival_calendar": Calendar,
            "hannover_christmas_calendar": SwitchedOff,
        },
        now=NOW,
    )
    assert str(result["source_outcomes"][-1]) == (
        "hannover_christmas_calendar discover_occasions: disabled, 0 usable, "
        "completion unknown (enabled = False)"
    )
    assert publication_refusal(result) is None
    assert "Critical occasion discovery hannover_christmas_calendar is disabled" in (
        caplog.text
    )


def test_a_failed_import_is_reported_and_named_in_the_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The broken module never registered, so the registry lacks its source.
    monkeypatch.setattr(
        aggregator,
        "get_all_sources",
        lambda: {"venue": Venue, "hannover_festival_calendar": Calendar},
    )
    monkeypatch.setattr(
        aggregator,
        "IMPORT_FAILURES",
        {"festivals.hannover_christmas": SyntaxError("invalid syntax")},
    )
    result = fetch_all_events(now=NOW)
    assert str(result["source_outcomes"][0]) == (
        "festivals.hannover_christmas import: failed, 0 usable, completion "
        "incomplete (SyntaxError: invalid syntax)"
    )
    assert publication_refusal(result) == (
        "missing critical occasion discovery: hannover_christmas_calendar "
        "(festivals.hannover_christmas import: failed, 0 usable, completion "
        "incomplete (SyntaxError: invalid syntax))"
    )


def test_a_broken_ordinary_module_stays_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import failures are recorded per module; the others still load."""
    real_import = sources.importlib.import_module
    broken = "boringhannover.sources.concerts.broncos"

    def import_module(name: str) -> object:
        if name == broken:
            raise SyntaxError("invalid syntax")
        return real_import(name)

    monkeypatch.setattr(sources.importlib, "import_module", import_module)
    monkeypatch.setattr(sources, "IMPORT_FAILURES", {})
    discovered = sources.discover_sources()
    # Every other module still imports; only the broken one is recorded.
    modules = sum(
        1
        for path in sources.Path(sources.__file__).parent.glob("*/[!_]*.py")
        if path.parent.name in {"cinema", "concerts", "festivals", "sports"}
    )
    assert list(sources.IMPORT_FAILURES) == ["concerts.broncos"]
    assert discovered == modules - 1

    outcomes = [
        SourceOutcome.failed("concerts.broncos", "import", SyntaxError("x")),
        SourceOutcome("venue", "fetch", "success", 1, "unknown"),
        *(
            SourceOutcome(name, "discover_occasions", "empty", 0, "complete")
            for name in CRITICAL_DISCOVERY
        ),
    ]
    events = {"movies_this_week": [], "big_events_radar": [object()]}
    assert publication_refusal({**events, "source_outcomes": outcomes}) is None
