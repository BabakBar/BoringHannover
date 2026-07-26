"""Regression tests for compact City Occasion notification output."""

from __future__ import annotations

from datetime import datetime

from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.notifier import format_message


def test_notification_summarizes_occasion_instead_of_dumping_programme() -> None:
    programme = [
        Event(
            title=f"Programme item {index}",
            date=datetime(2026, 7, 28, 19, index, tzinfo=BERLIN_TZ),
            venue="Maschsee-Bühne",
            url=f"https://example.com/{index}",
            category="radar",
            metadata={
                "occasion_id": "maschseefest-2026",
                "event_type": "festival",
            },
        )
        for index in range(20)
    ]
    regular = Event(
        title="Regular event",
        date=datetime(2026, 7, 29, 20, 0, tzinfo=BERLIN_TZ),
        venue="Faust",
        url="https://example.com/regular",
        category="radar",
    )

    result = format_message(
        {
            "movies_this_week": [],
            "big_events_radar": [*programme, regular],
        },
        now=datetime(2026, 7, 26, 12, 0, tzinfo=BERLIN_TZ),
    )

    assert "*Special in Hannover*" in result
    assert "*Maschseefest*" in result
    assert "20 programme items" in result
    assert "Programme item 0" not in result
    assert "Regular event" in result
