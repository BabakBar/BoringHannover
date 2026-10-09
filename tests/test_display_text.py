"""Tests for reader-facing text: word-boundary truncation and event-type keys."""

from __future__ import annotations

import pytest

from boringhannover.sanitize import sanitize_text, truncate_text


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
