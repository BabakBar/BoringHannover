"""Notification module for message formatting and delivery.

Formats events into a structured Telegram message with two sections:
1. "Movies (This Week)" - OV movies at Astor Cinema
2. "On The Radar" - Big upcoming concerts and events
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import httpx

from kinoweek.config import TELEGRAM_MESSAGE_MAX_LENGTH
from kinoweek.models import Event
from kinoweek.output import OutputManager, export_all_formats

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "format_message",
    "send_telegram_message",
    "save_to_file",
    "save_all_formats",
    "notify",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Type Definitions
# =============================================================================


class EventsData(TypedDict):
    """Structure for categorized event data."""

    movies_this_week: list[Event]
    big_events_radar: list[Event]


# =============================================================================
# Language Display Mapping
# =============================================================================

_LANGUAGE_ABBREVIATIONS: dict[str, str] = {
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

_VENUE_ABBREVIATIONS: dict[str, str] = {
    "ZAG Arena": "ZAG Arena",
    "Swiss Life Hall": "Swiss Life Hall",
    "Capitol Hannover": "Capitol",
}

# German day names for nice formatting
_GERMAN_DAYS: dict[int, str] = {
    0: "Mo",
    1: "Di",
    2: "Mi",
    3: "Do",
    4: "Fr",
    5: "Sa",
    6: "So",
}

_GERMAN_MONTHS: dict[int, str] = {
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


def _abbreviate_language(language: str) -> str:
    """Convert language string to compact abbreviation.

    Args:
        language: Full language string (e.g., "Sprache: Englisch").

    Returns:
        Abbreviated string (e.g., "EN").
    """
    result = language
    for full, abbrev in _LANGUAGE_ABBREVIATIONS.items():
        result = result.replace(full, abbrev)
    return result


def _abbreviate_venue(venue: str) -> str:
    """Convert venue name to compact abbreviation.

    Args:
        venue: Full venue name.

    Returns:
        Abbreviated venue name.
    """
    return _VENUE_ABBREVIATIONS.get(venue, venue)


def _format_duration(minutes: int) -> str:
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


def _format_movie_metadata(event: Event) -> list[str]:
    """Format movie metadata into display parts.

    Args:
        event: Movie event with metadata.

    Returns:
        List of formatted metadata parts (duration, rating, etc.).
    """
    parts: list[str] = []
    metadata = event.metadata

    duration = metadata.get("duration", 0)
    if duration:
        parts.append(_format_duration(int(duration)))

    rating = metadata.get("rating", 0)
    if rating:
        parts.append(f"FSK{rating}")

    return parts


def _format_concert_date(event: Event) -> str:
    """Format concert date in a nice, expanded format.

    Args:
        event: Concert event.

    Returns:
        Formatted date like "Sa, 29. Nov" or "Fr, 13. Jan 2026".
    """
    dt = event.date
    day_name = _GERMAN_DAYS.get(dt.weekday(), "")
    month_name = _GERMAN_MONTHS.get(dt.month, "")

    # Include year if not current year
    if dt.year != datetime.now().year:
        return f"{day_name}, {dt.day}. {month_name} {dt.year}"
    return f"{day_name}, {dt.day}. {month_name}"


# =============================================================================
# Message Formatting
# =============================================================================


def format_message(events_data: EventsData) -> str:
    """Format events into a Telegram-ready message.

    Creates a two-section message with movies and upcoming concerts,
    formatted with Telegram Markdown.

    Args:
        events_data: Dictionary with categorized event lists.

    Returns:
        Formatted message string ready for Telegram.
    """
    movies = events_data.get("movies_this_week", [])
    radar = events_data.get("big_events_radar", [])

    week_num = datetime.now().isocalendar()[1]
    lines: list[str] = [f"*Hannover Week {week_num}*\n"]

    # Section 1: Movies
    lines.append(_format_movies_section(movies))
    lines.append("")

    # Section 2: Radar (Concerts)
    lines.append(_format_radar_section(radar))

    message = "\n".join(lines).strip()

    # Ensure message doesn't exceed Telegram limits
    if len(message) > TELEGRAM_MESSAGE_MAX_LENGTH:
        truncated = message[: TELEGRAM_MESSAGE_MAX_LENGTH - 20]
        message = truncated + "\n\n... (truncated)"

    return message


def _format_movies_section(movies: Sequence[Event]) -> str:
    """Format the movies section of the message.

    Args:
        movies: List of movie events.

    Returns:
        Formatted movies section.
    """
    lines: list[str] = ["*Movies (This Week)*"]

    if not movies:
        lines.append("_No OV movies this week_")
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
    meta_parts = _format_movie_metadata(event)
    if meta_parts:
        lines.append(f"  _{' | '.join(meta_parts)}_")

    # Time and language
    time_str = event.date.strftime("%H:%M")
    language = event.metadata.get("language", "")
    lang_display = _abbreviate_language(language)
    lines.append(f"  {time_str} ({lang_display})")

    return lines


def _format_radar_section(radar: Sequence[Event]) -> str:
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
    date_str = _format_concert_date(event)
    venue_short = _abbreviate_venue(event.venue)
    time_str = event.metadata.get("time", "20:00")

    lines.append(f"  {date_str} | {time_str} @ {venue_short}")

    return lines


# =============================================================================
# Telegram Integration
# =============================================================================


def send_telegram_message(message: str) -> bool:
    """Send message via Telegram Bot API.

    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.

    Args:
        message: Message text to send.

    Returns:
        True if message was sent successfully.

    Raises:
        ValueError: If required environment variables are not set.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        msg = "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set"
        raise ValueError(msg)

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()

            result = response.json()
            if result.get("ok"):
                logger.info("Telegram message sent successfully")
                return True

            logger.error("Telegram API error: %s", result)
            return False

    except httpx.RequestError as exc:
        logger.exception("Failed to send Telegram message: %s", exc)
        return False


# Backward compatibility alias
send_telegram = send_telegram_message


# =============================================================================
# File Output
# =============================================================================


def _event_to_dict(event: Event) -> dict:
    """Convert an Event to a JSON-serializable dictionary.

    Args:
        event: Event to convert.

    Returns:
        Dictionary representation of the event.
    """
    return {
        "title": event.title,
        "date": event.date.isoformat(),
        "venue": event.venue,
        "url": event.url,
        "category": event.category,
        "metadata": dict(event.metadata),
    }


def save_to_file(
    message: str,
    events_data: EventsData,
    output_dir: str | Path = "output",
) -> None:
    """Save message and event data to local files.

    Creates two files:
    - latest_message.txt: Human-readable formatted message
    - events.json: Structured event data in JSON format

    Args:
        message: Formatted message string.
        events_data: Dictionary of event lists.
        output_dir: Output directory path.
    """
    output_path = Path(output_dir)

    try:
        output_path.mkdir(parents=True, exist_ok=True)

        # Save formatted message
        message_file = output_path / "latest_message.txt"
        message_file.write_text(message, encoding="utf-8")

        # Save structured event data
        json_data = {
            "movies_this_week": [
                _event_to_dict(e)
                for e in events_data.get("movies_this_week", [])
            ],
            "big_events_radar": [
                _event_to_dict(e)
                for e in events_data.get("big_events_radar", [])
            ],
        }

        json_file = output_path / "events.json"
        json_file.write_text(
            json.dumps(json_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info("Results saved to %s/", output_path)

    except OSError as exc:
        logger.exception("Failed to save results: %s", exc)


def save_all_formats(
    events_data: EventsData,
    output_dir: str | Path = "output",
) -> dict[str, Path]:
    """Save all output formats (CSV, JSON, Markdown, Archive).

    Creates multiple files:
    - movies.csv: Flat movie showtimes
    - movies_grouped.csv: Unique movies with consolidated showtimes
    - concerts.csv: All concerts
    - events.json: Enhanced structured data
    - weekly_digest.md: Human-readable markdown
    - archive/YYYY-WXX.json: Weekly snapshot

    Args:
        events_data: Dictionary of event lists.
        output_dir: Output directory path.

    Returns:
        Dictionary mapping format names to output paths.
    """
    movies = events_data.get("movies_this_week", [])
    concerts = events_data.get("big_events_radar", [])

    return export_all_formats(movies, concerts, output_dir)


# =============================================================================
# Main Notification Interface
# =============================================================================


def notify(events_data: EventsData, *, local_only: bool = False) -> bool:
    """Send notification or save locally based on mode.

    In production mode (local_only=False), sends to Telegram and
    creates a backup. In development mode (local_only=True), saves
    to local files and prints to console.

    Args:
        events_data: Dictionary of categorized event lists.
        local_only: If True, save to files instead of sending to Telegram.

    Returns:
        True if notification was successful.
    """
    try:
        message = format_message(events_data)

        if local_only:
            # Save Telegram message format
            save_to_file(message, events_data)

            # Also export all enhanced formats (CSV, Markdown, Archive)
            output_paths = save_all_formats(events_data)
            logger.info("Results saved locally (development mode)")
            logger.info("Output files: %s", ", ".join(str(p) for p in output_paths.values()))

            print(f"\n{message}\n")
            print("\nAdditional outputs generated:")
            for fmt, path in output_paths.items():
                print(f"  - {fmt}: {path}")

            return True

        success = send_telegram_message(message)
        if success:
            # Create backup and full export when sending
            save_to_file(message, events_data, "backup")
            save_all_formats(events_data, "backup")
        return success

    except Exception as exc:
        logger.exception("Notification failed: %s", exc)
        return False
