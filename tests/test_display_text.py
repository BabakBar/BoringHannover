"""Tests for reader-facing text: word-boundary truncation and event-type keys."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from boringhannover.constants import BERLIN_TZ
from boringhannover.sanitize import sanitize_text, truncate_text
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
