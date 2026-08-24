"""Regression tests for fail-closed German month parsing (issue #28)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag

from boringhannover.date_parsing import UNKNOWN_MONTH_TOKEN, lookup_german_month
from boringhannover.sources.base import parse_venue_date
from boringhannover.sources.concerts.bei_chez_heinz import BeiChezHeinzSource
from boringhannover.sources.concerts.weltspiele import WeltspieleSource
from boringhannover.sources.concerts.zag_arena import ZAGArenaSource


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("Januar", 1),
        ("Februar", 2),
        ("März", 3),
        ("April", 4),
        ("Mai", 5),
        ("Juni", 6),
        ("Juli", 7),
        ("August", 8),
        ("September", 9),
        ("Oktober", 10),
        ("November", 11),
        ("Dezember", 12),
        ("Jan", 1),
        ("Feb", 2),
        ("Mär", 3),
        ("Mar", 3),
        ("Apr", 4),
        ("Jun", 6),
        ("Jul", 7),
        ("Aug", 8),
        ("SEP", 9),
        ("OKT", 10),
        ("Oct", 10),
        ("Nov", 11),
        ("Dez", 12),
        ("Dec", 12),
    ],
)
def test_lookup_german_month_recognises_supported_tokens(
    token: str, expected: int
) -> None:
    assert lookup_german_month(token) == expected


@pytest.mark.parametrize("token", ["", "   ", "Foo", "Septembre", "Settembre"])
def test_lookup_german_month_rejects_unknown_tokens(token: str) -> None:
    assert lookup_german_month(token) is None


def test_lookup_german_month_is_pure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="boringhannover.date_parsing"):
        assert lookup_german_month("unknown") is None

    assert caplog.records == []


@pytest.mark.parametrize(
    ("raw_value", "month"),
    [("05SEP2026", 9), ("16OKT2026", 10), ("03NOV2026", 11)],
)
def test_parse_venue_date_accepts_observed_month_formats(
    raw_value: str, month: int
) -> None:
    result = parse_venue_date(raw_value, source_key="swiss_life_hall")

    assert result is not None
    assert result.month == month


def test_parse_venue_date_rejects_unknown_month_with_full_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_value = "AB22XXX2025"

    with caplog.at_level(logging.WARNING, logger="boringhannover.date_parsing"):
        result = parse_venue_date(raw_value, source_key="capitol_hannover")

    assert result is None
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.date_parse_failure == {
        "code": UNKNOWN_MONTH_TOKEN,
        "sourceKey": "capitol_hannover",
        "field": "start",
        "rawValue": raw_value,
        "normalizedToken": "xxx",
    }
    assert raw_value in record.getMessage()


def test_parse_venue_date_returns_none_when_pattern_does_not_match() -> None:
    assert parse_venue_date("not a date", source_key="test") is None
    assert parse_venue_date("", source_key="test") is None


class TestZagArenaDayMonthFallback:
    @staticmethod
    def _item(day: str, month: str) -> Tag:
        html = (
            '<div class="wpem-event-layout-wrapper">'
            f'<span class="wpem-date">{day}</span>'
            f'<span class="wpem-month">{month}</span>'
            "</div>"
        )
        item = BeautifulSoup(html, "html.parser").select_one(
            ".wpem-event-layout-wrapper"
        )
        assert item is not None
        return item

    def test_accepts_observed_punctuated_abbreviation(self) -> None:
        event_date, _time, _confidence = ZAGArenaSource()._parse_date(
            self._item("22", "Sep.")
        )

        assert event_date is not None
        assert event_date.month == 9
        assert event_date.day == 22

    def test_rejects_unknown_month_with_full_diagnostic(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="boringhannover.date_parsing"):
            event_date, _time, _confidence = ZAGArenaSource()._parse_date(
                self._item("22", "Xyz.")
            )

        assert event_date is None
        assert caplog.records[0].date_parse_failure["rawValue"] == "22 Xyz."

    def test_malformed_month_cannot_reach_an_event(self) -> None:
        html = (
            '<div class="wpem-event-layout-wrapper">'
            '<div class="wpem-heading-text">Mystery Show</div>'
            '<span class="wpem-date">22</span>'
            '<span class="wpem-month">Xyz</span>'
            '<a class="wpem-event-action-url" href="/event/mystery">Tickets</a>'
            "</div>"
        )
        item = BeautifulSoup(html, "html.parser").select_one(
            ".wpem-event-layout-wrapper"
        )
        assert item is not None

        assert ZAGArenaSource()._parse_event(item) is None


def test_bei_chez_heinz_rejects_unknown_month_with_date_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="boringhannover.date_parsing"):
        event_date, _time, _confidence = BeiChezHeinzSource()._parse_date_time(
            "Samstag 22. Foobar 2025 | Beginn: 20.00 Uhr"
        )

    assert event_date is None
    assert caplog.records[0].date_parse_failure["rawValue"] == "22. Foobar 2025"


def test_weltspiele_rejects_unknown_month_with_full_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_value = "Sat 27 Septembre 22:00-10:00"

    with caplog.at_level(logging.WARNING, logger="boringhannover.date_parsing"):
        result = WeltspieleSource()._parse_show_date(raw_value)

    assert result is None
    assert caplog.records[0].date_parse_failure["rawValue"] == raw_value


def test_sources_do_not_read_german_month_map_directly() -> None:
    sources_dir = Path(__file__).parents[1] / "src" / "boringhannover" / "sources"
    direct_users = [
        path.relative_to(sources_dir)
        for path in sources_dir.rglob("*.py")
        if "GERMAN_MONTH_MAP" in path.read_text(encoding="utf-8")
    ]

    assert direct_users == []
