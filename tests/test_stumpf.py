"""Regression coverage for Stumpf events from the punk aggregator."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from boringhannover.sources.concerts.punkrock_konzerte import (
    PunkrockKonzerteSource,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_stumpf_event_uses_the_official_venue_address() -> None:
    source = PunkrockKonzerteSource()
    soup = BeautifulSoup(
        (FIXTURES / "stumpf_event.html").read_text(encoding="utf-8"),
        "html.parser",
    )

    events = source._parse_events(soup)

    assert len(events) == 1
    assert events[0].title == "Fearskaper"
    assert events[0].venue == source.STUMPF_VENUE
    assert events[0].metadata["address"] == source.STUMPF_ADDRESS
