"""Tests for official City Occasion discovery."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from boringhannover.sources import get_source
from boringhannover.sources.festivals.hannover_calendar import (
    HannoverFestivalCalendarSource,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_calendar_discovers_city_occasions_and_excludes_region() -> None:
    source = HannoverFestivalCalendarSource()
    html = (FIXTURES / "hannover_festivals.html").read_text(encoding="utf-8")

    occasions = source._parse_calendar(html)

    assert [occasion.slug for occasion in occasions] == [
        "maschseefest-hannover-2026",
        "fahrmannsfest-2026",
    ]

    maschseefest = occasions[0]
    assert maschseefest.start_date == date(2026, 7, 23)
    assert maschseefest.end_date == date(2026, 8, 9)
    assert maschseefest.location == "Maschseefest"
    assert maschseefest.image_url.endswith("/maschsee-large.jpg")
    assert maschseefest.source_url.startswith("https://www.hannover.de/")

    faehrmannsfest = occasions[1]
    assert faehrmannsfest.start_date == date(2026, 7, 31)
    assert faehrmannsfest.end_date == date(2026, 7, 31)
    assert faehrmannsfest.description.startswith("Das alternative")


def test_discovery_source_is_registered_without_timeline_events() -> None:
    source_class = get_source("hannover_festival_calendar")

    assert source_class is HannoverFestivalCalendarSource
    assert source_class.source_type == "occasion"
    assert source_class().fetch() == []


def test_parse_detail_end_date_uses_final_official_appointment() -> None:
    end_date = HannoverFestivalCalendarSource._parse_detail_end_date(
        """
        <div class="details">
          <div class="detail-row">
            <div class="detail-cell"><p>Termine</p></div>
            <div class="detail-cell">
              <p>31.07.2026 ab 16:30 Uhr</p>
              <p>01.08.2026 ab 15:00 Uhr</p>
              <p>02.08.2026 ab 15:30 Uhr</p>
            </div>
          </div>
        </div>
        """
    )

    assert end_date == date(2026, 8, 2)
