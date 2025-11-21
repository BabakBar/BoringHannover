"""Notification module for message formatting and delivery.

Formats events into a structured Telegram message with three sections:
1. "Movies (This Week)" - OV movies at Astor Cinema
2. "Culture (This Week)" - Opera, ballet, theater events
3. "On The Radar" - Big upcoming concerts and events
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

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "format_message",
    "send_telegram_message",
    "save_to_file",
    "notify",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Type Definitions
# =============================================================================


class EventsData(TypedDict):
    """Structure for categorized event data."""

    movies_this_week: list[Event]
    culture_this_week: list[Event]
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
    "Staatstheater Hannover": "Staatstheater",
    "ZAG Arena": "ZAG",
    "Swiss Life Hall": "SLH",
    "Expo Plaza": "Expo",
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


# =============================================================================
# Message Formatting
# =============================================================================


def format_message(events_data: EventsData) -> str:
    """Format events into a Telegram-ready message.

    Creates a three-section message with movies, culture events,
    and upcoming big events, formatted with Telegram Markdown.

    Args:
        events_data: Dictionary with categorized event lists.

    Returns:
        Formatted message string ready for Telegram.
    """
    movies = events_data.get("movies_this_week", [])
    culture = events_data.get("culture_this_week", [])
    radar = events_data.get("big_events_radar", [])

    week_num = datetime.now().isocalendar()[1]
    lines: list[str] = [f"*Hannover Week {week_num}*\n"]

    # Section 1: Movies
    lines.append(_format_movies_section(movies))
    lines.append("")

    # Section 2: Culture
    lines.append(_format_culture_section(culture))
    lines.append("")

    # Section 3: Radar
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


def _format_culture_section(culture: Sequence[Event]) -> str:
    """Format the culture section of the message.

    Args:
        culture: List of culture events.

    Returns:
        Formatted culture section.
    """
    lines: list[str] = ["*Culture (This Week)*"]

    if not culture:
        lines.append("_No culture events this week_")
        return "\n".join(lines)

    for event in culture:
        time_str = event.format_time()
        venue_short = _abbreviate_venue(event.venue)
        lines.append(f"  *{event.title}*")
        lines.append(f"  {time_str} @ {venue_short}")

    return "\n".join(lines)


def _format_radar_section(radar: Sequence[Event]) -> str:
    """Format the radar (big events) section of the message.

    Args:
        radar: List of upcoming big events.

    Returns:
        Formatted radar section.
    """
    lines: list[str] = ["*On The Radar (Big Events)*"]

    if not radar:
        lines.append("_No big events on radar_")
        return "\n".join(lines)

    for event in radar:
        date_str = event.format_date_long()
        venue_short = _abbreviate_venue(event.venue)
        lines.append(f"  *{event.title}*")
        lines.append(f"  {date_str} @ {venue_short}")

    return "\n".join(lines)


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
            "culture_this_week": [
                _event_to_dict(e)
                for e in events_data.get("culture_this_week", [])
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
            save_to_file(message, events_data)
            logger.info("Results saved locally (development mode)")
            print(f"\n{message}\n")
            return True

        success = send_telegram_message(message)
        if success:
            # Create backup even when sending
            save_to_file(message, events_data, "backup")
        return success

    except Exception as exc:
        logger.exception("Notification failed: %s", exc)
        return False
