"""A cancelled listing never publishes as available (#134)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from boringhannover.availability import listing_status
from boringhannover.constants import BERLIN_TZ
from boringhannover.exporters import export_web_json
from boringhannover.sources.concerts.zag_arena import ZAGArenaSource


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    ("title", "status", "published"),
    [
        # ZAG Arena announced this cancellation only in the title.
        ("KONSTANTINOS ARGIROS \u2013 ABGESAGT", None, "cancelled"),
        ("Konzert fällt aus", None, "cancelled"),
        ("Lesung entfällt", None, "cancelled"),
        ("Show CANCELLED", None, "cancelled"),
        ("TESTKONZERT \u2013 VERSCHOBEN", None, "postponed"),
        # The venue's own wording beats a sold-out flag on the same card.
        ("Tour \u2013 ABGESAGT", "sold_out", "cancelled"),
        # Explicit adapter statuses stand.
        ("Show", "cancelled", "cancelled"),
        ("Show", "postponed", "postponed"),
        ("Show", "rescheduled", "rescheduled"),
        ("Show", "sold_out", "sold_out"),
        ("Show", "available", "available"),
        # No evidence is not availability.
        ("Show", None, "unknown"),
        ("Show", "", "unknown"),
        ("Show", "on sale soon", "unknown"),
        # Whole words only.
        ("Unabgesagt", None, "unknown"),
        ("Verschobene Realitäten", None, "unknown"),
    ],
)
def test_listing_status(title: str, status: str | None, published: str) -> None:
    assert listing_status(title, status) == published


def test_zag_cancellation_in_the_title_publishes_as_cancelled(tmp_path: Path) -> None:
    html = (FIXTURES / "zag_arena_listing.html").read_text(encoding="utf-8")
    events = ZAGArenaSource()._parse_events(BeautifulSoup(html, "html.parser"))
    assert [event.title for event in events] == [
        "NIGHT OF THE PROMS",
        "KONSTANTINOS ARGIROS \u2013 ABGESAGT",
        "PUR",
        "TESTKONZERT \u2013 VERSCHOBEN",
    ]
    # The adapter reports what the card states: nothing about availability.
    assert all("status" not in event.metadata for event in events)

    export_web_json(
        [],
        events,
        tmp_path,
        48,
        2026,
        generated_at=datetime(2026, 11, 22, 19, 0, tzinfo=BERLIN_TZ),
    )
    concerts = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))[
        "concerts"
    ]
    assert {row["title"]: row["status"] for row in concerts} == {
        "KONSTANTINOS ARGIROS \u2013 ABGESAGT": "cancelled",
        "NIGHT OF THE PROMS": "unknown",
        "PUR": "unknown",
        "TESTKONZERT \u2013 VERSCHOBEN": "postponed",
    }
    # The source wording stays in the title.
    assert "available" not in {row["status"] for row in concerts}
