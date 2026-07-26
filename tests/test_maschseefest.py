"""Tests for the seasonal Maschseefest programme source."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup

from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import CONFIRMED_TIME
from boringhannover.sources.festivals.maschseefest import MaschseefestSource


FIXTURES = Path(__file__).parent / "fixtures"


def test_source_is_active_only_near_the_2026_season() -> None:
    source = MaschseefestSource()

    assert source._is_active(date(2026, 7, 8))
    assert source._is_active(date(2026, 8, 9))
    assert not source._is_active(date(2026, 7, 7))
    assert not source._is_active(date(2026, 8, 10))


def test_parse_inventory_keeps_only_canonical_event_links() -> None:
    source = MaschseefestSource()
    payload = json.loads(
        (FIXTURES / "maschseefest_inventory.json").read_text(encoding="utf-8")
    )

    inventory = source._parse_inventory(payload)

    assert inventory == {
        "https://www.maschseefest.de/veranstaltungen/country-night-mit-sascha-salvati/": (
            "Country Night mit Sascha Salvati"
        ),
        "https://www.maschseefest.de/veranstaltungen/np-sommerfestival-10/": (
            "NP-Sommerfestival"
        ),
    }


def test_parse_programme_page_uses_inventory_and_marks_incomplete_cards() -> None:
    source = MaschseefestSource()
    soup = BeautifulSoup(
        (FIXTURES / "maschseefest_programme.html").read_text(encoding="utf-8"),
        "html.parser",
    )
    inventory = {
        "https://www.maschseefest.de/veranstaltungen/country-night-mit-sascha-salvati/": (
            "Country Night mit Sascha Salvati"
        ),
        "https://www.maschseefest.de/veranstaltungen/np-sommerfestival-10/": (
            "NP-Sommerfestival"
        ),
    }

    entries, total_pages = source._parse_programme_page(soup, inventory)

    assert total_pages == 2
    assert len(entries) == 2

    confirmed = entries[0]
    assert confirmed.title == "Country Night mit Sascha Salvati"
    assert confirmed.date == date(2026, 7, 31)
    assert confirmed.start_time == "21:00"
    assert confirmed.end_time == "23:00"
    assert confirmed.venue == "Maschsee-Bühne"
    assert confirmed.description.startswith("Country-Star")
    assert confirmed.image_url.endswith("/country.jpg")
    assert not source._needs_detail(confirmed)

    incomplete = entries[1]
    assert incomplete.title == "NP-Sommerfestival"
    assert incomplete.start_time is None
    assert incomplete.venue is None
    assert source._needs_detail(incomplete)


def test_parse_detail_page_enriches_an_incomplete_programme_card() -> None:
    source = MaschseefestSource()
    programme_soup = BeautifulSoup(
        (FIXTURES / "maschseefest_programme.html").read_text(encoding="utf-8"),
        "html.parser",
    )
    detail_soup = BeautifulSoup(
        (FIXTURES / "maschseefest_detail.html").read_text(encoding="utf-8"),
        "html.parser",
    )
    url = "https://www.maschseefest.de/veranstaltungen/np-sommerfestival-10/"
    entries, _ = source._parse_programme_page(
        programme_soup,
        {
            url: "NP-Sommerfestival",
            "https://www.maschseefest.de/veranstaltungen/country-night-mit-sascha-salvati/": (
                "Country Night mit Sascha Salvati"
            ),
        },
    )

    enriched = source._enrich_entry(entries[1], source._parse_detail_page(detail_soup))
    event = source._to_event(enriched)

    assert event.title == "NP-Sommerfestival"
    assert event.date == datetime(2026, 8, 9, 16, 0, tzinfo=BERLIN_TZ)
    assert event.venue == "Maschsee-Bühne"
    assert event.category == "radar"
    assert event.metadata["time"] == "16:00"
    assert event.metadata["time_confidence"] == CONFIRMED_TIME
    assert event.metadata["event_type"] == "festival"
    assert event.metadata["occasion_id"] == "maschseefest-2026"
    assert event.metadata["programme_category"] == "Music"
    assert event.metadata["end_time"] == "22:00"
    assert event.metadata["subtitle"] == "Das NP-Sommerfestival am Nordufer."
    assert event.metadata["image_url"].endswith("/sommerfestival.jpg")


def test_to_event_uses_safe_fallbacks_without_inventing_a_start_time() -> None:
    source = MaschseefestSource()
    soup = BeautifulSoup(
        (FIXTURES / "maschseefest_programme.html").read_text(encoding="utf-8"),
        "html.parser",
    )
    url = "https://www.maschseefest.de/veranstaltungen/np-sommerfestival-10/"
    entries, _ = source._parse_programme_page(soup, {url: "NP-Sommerfestival"})

    event = source._to_event(entries[0])

    assert event.date == datetime(2026, 8, 9, 12, 0, tzinfo=BERLIN_TZ)
    assert event.venue == "Maschseefest"
    assert event.metadata["time_confidence"] == "fallback"
