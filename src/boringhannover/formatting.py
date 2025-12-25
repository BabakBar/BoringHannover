"""Message formatting helpers for BoringHannover.

Contains language abbreviations, date formatting, and message section builders.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from boringhannover.constants import BERLIN_TZ

if TYPE_CHECKING:
    from collections.abc import Sequence

    from boringhannover.models import Event

__all__ = [
    "GERMAN_DAYS",
    "GERMAN_MONTHS",
    "abbreviate_language",
    "abbreviate_venue",
    "format_concert_date",
    "format_duration",
    "format_movie_metadata",
    "format_movies_section",
    "format_radar_section",
]


# =============================================================================
# Language Display Mapping
# =============================================================================

LANGUAGE_ABBREVIATIONS: dict[str, str] = {
    "Sprache: ": "",
    "Untertitel: ": "UT:",
    "Englisch": "EN",
    "Japanisch": "JP",
    "Italienisch": "IT",
    "Spanisch": "ES",
    "Russisch": "RU",
    "Deutsch": "DE",
    "Französisch": "FR",
    "Koreanisch": "KR",
    "Chinesisch": "ZH",
}

VENUE_ABBREVIATIONS: dict[str, str] = {
    "ZAG Arena": "ZAG Arena",
    "Swiss Life Hall": "Swiss Life Hall",
    "Capitol Hannover": "Capitol",
}

# German day names for nice formatting
GERMAN_DAYS: dict[int, str] = {
    0: "Mo",
    1: "Di",
    2: "Mi",
    3: "Do",
    4: "Fr",
    5: "Sa",
    6: "So",
}

GERMAN_MONTHS: dict[int, str] = {
    1: "Jan",
    2: "Feb",
    3: "Mär",
    4: "Apr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Okt",
    11: "Nov",
    12: "Dez",
}


# =============================================================================
# Formatting Helpers
# =============================================================================


def abbreviate_language(language: str) -> str:
    """Convert language string to compact abbreviation.

    Args:
        language: Full language string (e.g., "Sprache: Englisch").

    Returns:
        Abbreviated string (e.g., "EN").
    """
    result = language
    for full, abbrev in LANGUAGE_ABBREVIATIONS.items():
        result = result.replace(full, abbrev)
    return result


def abbreviate_venue(venue: str) -> str:
    """Convert venue name to compact abbreviation.

    Args:
        venue: Full venue name.

    Returns:
        Abbreviated venue name.
    """
    return VENUE_ABBREVIATIONS.get(venue, venue)


def format_duration(minutes: int) -> str:
    """Format duration in minutes to human-readable string.

    Args:
        minutes: Duration in minutes.

    Returns:
        Formatted string like "2h17m" or "45m".
    """
    if minutes <= 0:
        return ""

    hours, mins = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h{mins}m" if mins else f"{hours}h"
    return f"{mins}m"


def format_movie_metadata(event: Event) -> list[str]:
    """Format movie metadata into display parts.

    Args:
        event: Movie event with metadata.

    Returns:
        List of formatted metadata parts (duration, rating, etc.).
    """
    parts: list[str] = []
    metadata = event.metadata

    duration = metadata.get("duration", 0)
    if duration and isinstance(duration, int):
        parts.append(format_duration(duration))

    rating = metadata.get("rating", 0)
    if rating:
        parts.append(f"FSK{rating}")

    return parts


def format_concert_date(event: Event) -> str:
    """Format concert date in a nice, expanded format.

    Args:
        event: Concert event.

    Returns:
        Formatted date like "Sa, 29. Nov" or "Fr, 13. Jan 2026".
    """
    dt = event.date
    day_name = GERMAN_DAYS.get(dt.weekday(), "")
    month_name = GERMAN_MONTHS.get(dt.month, "")

    # Include year if not current year
    if dt.year != datetime.now(BERLIN_TZ).year:
        return f"{day_name}, {dt.day}. {month_name} {dt.year}"
    return f"{day_name}, {dt.day}. {month_name}"


# =============================================================================
# Section Formatting
# =============================================================================


def _format_movie_entry(event: Event) -> list[str]:
    """Format a single movie entry.

    Args:
        event: Movie event to format.

    Returns:
        List of lines for this movie entry.
    """
    lines: list[str] = []

    # Title with year
    title = event.title
    year = event.metadata.get("year")
    if year:
        title = f"{title} ({year})"

    lines.append(f"  *{title}*")

    # Metadata line
    meta_parts = format_movie_metadata(event)
    if meta_parts:
        lines.append(f"  _{' | '.join(meta_parts)}_")

    # Time and language
    time_str = event.date.strftime("%H:%M")
    language = event.metadata.get("language", "")
    lang_display = abbreviate_language(str(language)) if language else ""
    lines.append(f"  {time_str} ({lang_display})")

    return lines


def _format_concert_entry(event: Event) -> list[str]:
    """Format a single concert entry with expanded date.

    Args:
        event: Concert event to format.

    Returns:
        List of lines for this concert entry.
    """
    lines: list[str] = []

    # Title
    lines.append(f"  *{event.title}*")

    # Date and venue on same line
    date_str = format_concert_date(event)
    venue_short = abbreviate_venue(event.venue)
    time_str = event.metadata.get("time", "20:00")

    lines.append(f"  {date_str} | {time_str} @ {venue_short}")

    return lines


def format_movies_section(movies: Sequence[Event]) -> str:
    """Format the movies section of the message.

    Args:
        movies: List of movie events.

    Returns:
        Formatted movies section.
    """
    lines: list[str] = ["*Movies*"]

    if not movies:
        lines.append("_No OV movies found_")
        return "\n".join(lines)

    # Group by date for better readability
    movies_by_date: dict[str, list[Event]] = {}
    for event in movies:
        date_key = event.format_date_short()
        if date_key not in movies_by_date:
            movies_by_date[date_key] = []
        movies_by_date[date_key].append(event)

    for date_str, date_events in movies_by_date.items():
        lines.append(f"\n*{date_str}*")
        for event in date_events:
            lines.extend(_format_movie_entry(event))

    return "\n".join(lines)


def format_radar_section(radar: Sequence[Event]) -> str:
    """Format the radar (concerts/big events) section of the message.

    Args:
        radar: List of upcoming big events.

    Returns:
        Formatted radar section.
    """
    lines: list[str] = ["*On The Radar*"]

    if not radar:
        lines.append("_No upcoming events_")
        return "\n".join(lines)

    for event in radar:
        lines.extend(_format_concert_entry(event))

    return "\n".join(lines)
