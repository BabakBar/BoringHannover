"""Tests for the first-party LUX programme source."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import CONFIRMED_TIME
from boringhannover.sources import get_all_sources
from boringhannover.sources.concerts.lux import LuxSource


FIXTURE = Path(__file__).parent / "fixtures" / "lux_programme.html"
NOW = datetime(2026, 7, 26, 12, 0, tzinfo=BERLIN_TZ)


def test_parse_programme_keeps_valid_first_party_events() -> None:
    soup = BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")

    events = LuxSource()._parse_events(soup, now=NOW)

    assert [event.title for event in events] == [
        "DRIVEN BY CLOCKWORK /W SUMMER GLOOM",
        "PON DE BEATS X RAMUNE RAVE",
        "MC BOMBER",
        "JANUARY FUTURE",
    ]

    concert = events[0]
    assert concert.date == datetime(2026, 8, 14, 20, 0, tzinfo=BERLIN_TZ)
    assert concert.url.endswith("/konzerte/driven-by-clockwork-w-summer-gloom/")
    assert concert.venue == "LUX"
    assert concert.metadata["time_confidence"] == CONFIRMED_TIME
    assert concert.metadata["event_type"] == "concert"
    assert concert.metadata["status"] == "available"
    assert concert.metadata["genre"] == "Punk / Hardcore"
    assert concert.metadata["genre_source"] == "programme_description"
    assert concert.metadata["price"] == "16 € zzgl. Geb."
    assert concert.metadata["address"] == "Schwarzer Bär 2, 30449 Hannover"
    assert concert.metadata["image_url"].endswith("/driven.jpg")

    club_night = events[1]
    assert club_night.date == datetime(2026, 8, 22, 22, 0, tzinfo=BERLIN_TZ)
    assert club_night.metadata["event_type"] == "party"
    assert "genre" not in club_night.metadata

    sold_out = events[2]
    assert sold_out.metadata["status"] == "sold_out"
    assert "price" not in sold_out.metadata


def test_parse_programme_handles_year_rollover() -> None:
    soup = BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")

    events = LuxSource()._parse_events(soup, now=NOW)
    future = next(event for event in events if event.title == "JANUARY FUTURE")

    assert future.date == datetime(2027, 1, 21, 20, 30, tzinfo=BERLIN_TZ)
    assert future.metadata["genre"] == "Rock"


def test_parse_programme_drops_cancelled_unresolved_and_malformed_entries() -> None:
    soup = BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")

    events = LuxSource()._parse_events(soup, now=NOW)
    titles = {event.title for event in events}

    assert "TRAUMATIN" not in titles
    assert "MICHÈL VON WUSSOW" not in titles
    assert "PAST EVENT" not in titles
    assert "MALFORMED EVENT" not in titles


def test_lux_source_is_registered() -> None:
    assert get_all_sources()["lux"] is LuxSource
