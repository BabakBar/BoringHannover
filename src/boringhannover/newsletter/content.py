"""Build the weekly edition content model from the canonical web artifact.

The email must never grow a second content path: everything it says comes from
``output/web_events.json``, the same file the website is built from.

Nothing here reads the clock. The covered window is derived from the artifact so
the same artifact always produces the same edition.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from boringhannover.event_time import UNKNOWN_TIME_LABEL
from boringhannover.newsletter.edition import build_edition_key


if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "DEFAULT_CITY_ID",
    "DEFAULT_LOCALE",
    "WINDOW_DAYS",
    "EditionContent",
    "EditionItem",
    "EditionSection",
    "build_edition_content",
]

DEFAULT_CITY_ID: Final[str] = "hannover"
DEFAULT_LOCALE: Final[str] = "en"
WINDOW_DAYS: Final[int] = 7
"""Days covered by one edition, counting the artifact generation day."""

_SECTION_TITLES: Final[dict[str, str]] = {
    "occasions": "Special in Hannover",
    "movies": "Original-version cinema",
    "radar": "On the radar",
}
_SECTION_ORDER: Final[tuple[str, ...]] = ("occasions", "movies", "radar")


@dataclass(frozen=True, slots=True)
class EditionItem:
    """One line of the edition: a screening, an event, or an occasion."""

    title: str
    date_display: str
    date_iso: str
    time: str
    venue: str
    url: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class EditionSection:
    """A titled group of items."""

    key: str
    title: str
    items: tuple[EditionItem, ...]


@dataclass(frozen=True, slots=True)
class EditionContent:
    """Everything one edition says, plus the identity derived from it."""

    key: str
    city_id: str
    locale: str
    year: int
    week: int
    window_start: date
    window_end: date
    generated_at: datetime
    sections: tuple[EditionSection, ...]
    revision: str

    @property
    def is_empty(self) -> bool:
        """True when the edition would carry no events at all."""
        return not any(section.items for section in self.sections)

    @property
    def item_count(self) -> int:
        """Total number of items across all sections."""
        return sum(len(section.items) for section in self.sections)


def _generated_at(artifact: Mapping[str, Any]) -> datetime:
    """Read the artifact generation timestamp, failing closed when unusable."""
    meta = artifact.get("meta")
    raw = meta.get("updatedAtISO") if isinstance(meta, Mapping) else None
    if not raw:
        msg = "Artifact has no meta.updatedAtISO; refusing to guess the edition window"
        raise ValueError(msg)
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError as exc:
        msg = f"Artifact meta.updatedAtISO is not an ISO timestamp: {raw!r}"
        raise ValueError(msg) from exc


def _parse_iso_date(raw: object) -> date | None:
    """Parse an ISO date, returning None rather than inventing one."""
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _format_day(day: date) -> str:
    """Format a date as 'Sat 29 Aug'."""
    return f"{day:%a} {day.day} {day:%b}"


def _join_note(parts: Iterable[str | None]) -> str:
    """Join present note fragments with the separator used across the site."""
    return " · ".join(part for part in parts if part)


def _movie_items(
    days: Iterable[Any],
    window_start: date,
    window_end: date,
) -> list[EditionItem]:
    """Flatten the per-day movie groups into items inside the window."""
    items: list[EditionItem] = []
    for day_group in days:
        if not isinstance(day_group, Mapping):
            continue
        day = _parse_iso_date(day_group.get("dateISO"))
        if day is None or not (window_start <= day <= window_end):
            continue
        for movie in day_group.get("movies") or ():
            if not isinstance(movie, Mapping):
                continue
            language = movie.get("language")
            subtitles = movie.get("subtitles")
            language_note = (
                f"{language} (subs {subtitles})"
                if language and subtitles
                else language or subtitles
            )
            items.append(
                EditionItem(
                    title=str(movie.get("title") or ""),
                    date_display=_format_day(day),
                    date_iso=day.isoformat(),
                    time=str(movie.get("time") or UNKNOWN_TIME_LABEL),
                    venue=str(movie.get("venue") or ""),
                    url=str(movie.get("url") or ""),
                    note=_join_note(
                        [
                            str(language_note) if language_note else None,
                            str(movie.get("duration") or "") or None,
                            str(movie.get("rating") or "") or None,
                        ]
                    ),
                )
            )
    return items


def _radar_items(
    concerts: Iterable[Any],
    window_start: date,
    window_end: date,
) -> list[EditionItem]:
    """Select radar events inside the window."""
    items: list[EditionItem] = []
    for concert in concerts:
        if not isinstance(concert, Mapping):
            continue
        day = _parse_iso_date(concert.get("dateISO"))
        if day is None or not (window_start <= day <= window_end):
            continue
        status = str(concert.get("status") or "available")
        items.append(
            EditionItem(
                title=str(concert.get("title") or ""),
                date_display=_format_day(day),
                date_iso=day.isoformat(),
                time=str(concert.get("time") or UNKNOWN_TIME_LABEL),
                venue=str(concert.get("venue") or ""),
                url=str(concert.get("url") or ""),
                note=_join_note(
                    [
                        str(concert.get("radarCategory") or "") or None,
                        str(concert.get("genre") or "") or None,
                        "Sold out" if status == "sold_out" else None,
                    ]
                ),
            )
        )
    return items


def _occasion_items(
    occasions: Iterable[Any],
    window_start: date,
    window_end: date,
) -> list[EditionItem]:
    """Select City Occasions overlapping the window."""
    items: list[EditionItem] = []
    for occasion in occasions:
        if not isinstance(occasion, Mapping):
            continue
        start = _parse_iso_date(occasion.get("startDate"))
        end = _parse_iso_date(occasion.get("endDate")) or start
        if start is None or end is None:
            continue
        if start > window_end or end < window_start:
            continue
        programme_count = occasion.get("programmeCount") or 0
        items.append(
            EditionItem(
                title=str(occasion.get("name") or ""),
                date_display=f"{_format_day(start)} - {_format_day(end)}",
                date_iso=start.isoformat(),
                time="",
                venue=str(occasion.get("location") or ""),
                url=str(occasion.get("sourceUrl") or ""),
                note=_join_note(
                    [
                        str(occasion.get("location") or "") or None,
                        f"{programme_count} programme items"
                        if programme_count
                        else None,
                    ]
                ),
            )
        )
    return items


def _sorted_section(key: str, items: list[EditionItem]) -> EditionSection | None:
    """Build a date-ordered section, or None when it would be empty."""
    if not items:
        return None
    ordered = sorted(items, key=lambda item: (item.date_iso, item.time, item.title))
    return EditionSection(key=key, title=_SECTION_TITLES[key], items=tuple(ordered))


def _compute_revision(
    key: str,
    window_start: date,
    window_end: date,
    sections: tuple[EditionSection, ...],
) -> str:
    """Hash what the edition says, not when it was generated."""
    payload = {
        "key": key,
        "window": [window_start.isoformat(), window_end.isoformat()],
        "sections": [
            {
                "key": section.key,
                "items": [
                    [
                        item.title,
                        item.date_iso,
                        item.time,
                        item.venue,
                        item.url,
                        item.note,
                    ]
                    for item in section.items
                ],
            }
            for section in sections
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_edition_content(
    artifact: Mapping[str, Any],
    *,
    city_id: str = DEFAULT_CITY_ID,
    locale: str = DEFAULT_LOCALE,
    window_days: int = WINDOW_DAYS,
) -> EditionContent:
    """Derive one edition from a canonical ``web_events.json`` payload.

    Args:
        artifact: Parsed ``web_events.json`` content.
        city_id: City slug for the edition key.
        locale: Language of this edition.
        window_days: Days covered, counting the generation day.

    Returns:
        The edition content model, including its stable key and revision.

    Raises:
        ValueError: If the artifact carries no usable generation timestamp.
    """
    generated_at = _generated_at(artifact)
    window_start = generated_at.date()
    window_end = window_start + timedelta(days=window_days - 1)

    candidates = {
        "occasions": _occasion_items(
            artifact.get("occasions") or (), window_start, window_end
        ),
        "movies": _movie_items(artifact.get("movies") or (), window_start, window_end),
        "radar": _radar_items(artifact.get("concerts") or (), window_start, window_end),
    }
    sections = tuple(
        section
        for key in _SECTION_ORDER
        if (section := _sorted_section(key, candidates[key])) is not None
    )

    key = build_edition_key(window_start, city_id=city_id, locale=locale)
    iso_year, iso_week, _ = window_start.isocalendar()

    return EditionContent(
        key=key,
        city_id=city_id,
        locale=locale,
        year=iso_year,
        week=iso_week,
        window_start=window_start,
        window_end=window_end,
        generated_at=generated_at,
        sections=sections,
        revision=_compute_revision(key, window_start, window_end, sections),
    )
