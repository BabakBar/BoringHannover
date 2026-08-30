"""Edition identity: stable keys and content-derived revisions."""

from __future__ import annotations

from datetime import date

import pytest

from boringhannover.newsletter.edition import build_edition_key


def test_edition_key_uses_iso_week_of_the_window_start() -> None:
    assert (
        build_edition_key(date(2026, 8, 27), city_id="hannover", locale="en")
        == "hannover:2026-W35:en"
    )


def test_edition_key_pads_single_digit_weeks() -> None:
    assert (
        build_edition_key(date(2026, 1, 8), city_id="hannover", locale="en")
        == "hannover:2026-W02:en"
    )


def test_edition_key_uses_iso_year_not_calendar_year() -> None:
    # 2026-12-31 is a Thursday in ISO week 53 of 2026; 2027-01-01 still belongs to it.
    assert (
        build_edition_key(date(2027, 1, 1), city_id="hannover", locale="en")
        == "hannover:2026-W53:en"
    )


@pytest.mark.parametrize("locale", ["", "EN", "en_US", "en us"])
def test_edition_key_rejects_locales_outside_the_canonical_form(locale: str) -> None:
    with pytest.raises(ValueError, match="locale"):
        build_edition_key(date(2026, 8, 27), city_id="hannover", locale=locale)


@pytest.mark.parametrize("city_id", ["", "Hannover", "hannover city"])
def test_edition_key_rejects_city_ids_outside_the_canonical_form(city_id: str) -> None:
    with pytest.raises(ValueError, match="city_id"):
        build_edition_key(date(2026, 8, 27), city_id=city_id, locale="en")
