"""Regression coverage for SV Arminia events from the punk aggregator."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from boringhannover.sources.concerts.punkrock_konzerte import (
    PunkrockKonzerteSource,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_arminia_venue_aliases_are_normalized_with_full_address() -> None:
    source = PunkrockKonzerteSource()
    soup = BeautifulSoup(
        (FIXTURES / "sv_arminia_events.html").read_text(encoding="utf-8"),
        "html.parser",
    )

    events = source._parse_events(soup)

    assert [event.title for event in events] == [
        "Labasheeda + die ueblichen",
        "Muck And The Mires",
    ]
    assert {event.venue for event in events} == {source.ARMINIA_VENUE}
    assert {event.metadata["address"] for event in events} == {source.ARMINIA_ADDRESS}
