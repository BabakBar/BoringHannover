"""Stable identity for one weekly email edition."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final


if TYPE_CHECKING:
    from datetime import date

__all__ = ["build_edition_key"]

_SLUG_PATTERN: Final = re.compile(r"^[a-z0-9-]+$")
_LOCALE_PATTERN: Final = re.compile(r"^[a-z]{2}$")


def build_edition_key(window_start: date, *, city_id: str, locale: str) -> str:
    """Build the edition key, e.g. ``hannover:2026-W35:en``.

    Args:
        window_start: First day the edition covers; its ISO week names the edition.
        city_id: Lowercase city slug, kept city-neutral for Boring Network reuse.
        locale: Two-letter lowercase language code.

    Returns:
        The canonical edition key.

    Raises:
        ValueError: If city_id or locale is not in canonical form.
    """
    if not _SLUG_PATTERN.match(city_id):
        msg = f"city_id must be a lowercase slug, got {city_id!r}"
        raise ValueError(msg)
    if not _LOCALE_PATTERN.match(locale):
        msg = f"locale must be a two-letter lowercase code, got {locale!r}"
        raise ValueError(msg)

    iso_year, iso_week, _ = window_start.isocalendar()
    return f"{city_id}:{iso_year}-W{iso_week:02d}:{locale}"
