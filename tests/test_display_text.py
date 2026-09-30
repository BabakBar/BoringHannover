"""Tests for reader-facing text: word-boundary truncation and event-type keys."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from bs4 import BeautifulSoup

from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sanitize import sanitize_text, truncate_text
from boringhannover.sources.concerts.faust import FaustSource
from boringhannover.sources.concerts.glocke import GlockseeSource
from boringhannover.sources.concerts.kulturpalast_linden import (
    KulturpalastLindenSource,
)


# Real LUX description that used to publish as "...das ebenfalls de".
LUX_TEXT = (
    "Sean Koch kehrt mit einem brandneuen Album und einer noch nie dagewesenen "
    "Show nach Europa zurück. Die „Time Will Tell“-Tour feiert die "
    "Veröffentlichung von Seans drittem Studioalbum, das ebenfalls denselben "
    "Namen trägt."
)


class TestTruncateText:
    def test_short_text_is_unchanged(self) -> None:
        assert truncate_text("Offenes Krökeln", 200) == "Offenes Krökeln"

    def test_text_at_exact_limit_is_unchanged(self) -> None:
        assert truncate_text("a" * 20, 20) == "a" * 20

    def test_cuts_at_word_boundary_with_ellipsis(self) -> None:
        result = truncate_text(LUX_TEXT, 200)

        assert len(result) <= 200
        assert result.endswith("ebenfalls…")
        assert LUX_TEXT.startswith(result.removesuffix("…"))

    def test_drops_trailing_punctuation_before_ellipsis(self) -> None:
        assert truncate_text("Workshops, Vorträge, Essen, Party", 20) == (
            "Workshops, Vorträge…"
        )

    def test_hard_cut_when_no_usable_space(self) -> None:
        result = truncate_text("x" * 300, 200)

        assert result == "x" * 199 + "…"

    @pytest.mark.parametrize("limit", [10, 50, 157, 200])
    def test_never_exceeds_limit(self, limit: int) -> None:
        assert len(truncate_text(LUX_TEXT, limit)) <= limit


def test_sanitize_text_truncates_on_word_boundary() -> None:
    result = sanitize_text(f"<p>{LUX_TEXT}</p>", 200)

    assert result.endswith("ebenfalls…")
    assert "..." not in result


def test_kulturpalast_first_line_keeps_whole_words() -> None:
    source = KulturpalastLindenSource()

    result = source._first_description_line(LUX_TEXT)

    assert result is not None
    assert result.endswith("ebenfalls…")


class TestGlockseeEventType:
    @staticmethod
    def _parse(event_type: object) -> str:
        now = datetime.now(BERLIN_TZ)
        data: dict[str, object] = {
            "title": [{"text": "Test Show"}],
            "datetime": (now + timedelta(days=3)).isoformat(),
        }
        if event_type is not None:
            data["event_type"] = event_type
        event = GlockseeSource()._parse_event({"uid": "x", "data": data}, now)
        assert event is not None
        return str(event.metadata["event_type"])

    @pytest.mark.parametrize("raw", [None, "", "Konzert", "konzert", " KONZERT "])
    def test_german_or_missing_type_becomes_concert(self, raw: object) -> None:
        assert self._parse(raw) == "concert"

    def test_other_types_pass_through(self) -> None:
        assert self._parse("party") == "party"


class TestFaustStartTime:
    @staticmethod
    def _parse(start_line: str) -> Event:
        html = (
            '<a href="/veranstaltungen/oktober/021026-puro-barrio.html">'
            "<span>Fr, 02.10.26</span><span>Puro Barrio</span>"
            f"<span>{start_line}</span></a>"
        )
        link = BeautifulSoup(html, "html.parser").a
        assert link is not None
        event = FaustSource()._parse_event(link, event_type="party")
        assert event is not None
        return event

    def test_confirmed_time_replaces_the_placeholder(self) -> None:
        event = self._parse("Beginn: 19:30 Uhr")

        assert (event.date.hour, event.date.minute) == (19, 30)

    def test_24_uhr_stays_on_its_day_and_sorts_last(self) -> None:
        event = self._parse("Einlass / Beginn: 24 Uhr")

        assert event.date.date().isoformat() == "2026-10-02"
        assert (event.date.hour, event.date.minute) == (23, 59)
        assert event.metadata["time"] == "24:00"

    def test_midnight_party_sorts_after_evening_concert(self) -> None:
        party = self._parse("Beginn: 24 Uhr")
        concert = self._parse("Beginn: 21 Uhr")

        assert sorted([party, concert], key=lambda e: e.date) == [concert, party]

    def test_unconfirmed_time_keeps_the_placeholder(self) -> None:
        event = self._parse("Eintritt frei")

        assert (event.date.hour, event.date.minute) == (20, 0)
