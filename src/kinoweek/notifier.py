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
from kinoweek.formatting import format_movies_section, format_radar_section
from kinoweek.models import Event
from kinoweek.output import export_all_formats

if TYPE_CHECKING:
    pass

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
    lines.append(format_movies_section(movies))
    lines.append("")

    # Section 2: Radar (Concerts)
    lines.append(format_radar_section(radar))

    message = "\n".join(lines).strip()

    # Ensure message doesn't exceed Telegram limits
    if len(message) > TELEGRAM_MESSAGE_MAX_LENGTH:
        truncated = message[: TELEGRAM_MESSAGE_MAX_LENGTH - 20]
        message = truncated + "\n\n... (truncated)"

    return message


# =============================================================================
# Telegram Integration
# =============================================================================


def send_telegram_message(message: str) -> bool:
    """Send message via Telegram Bot API.

    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.

    Security Note (BS-3): Uses base_url pattern to prevent token leakage
    in exception messages. If httpx raises an error, the full URL (with token)
    won't appear in logs or tracebacks.

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

    # BS-3: Use base_url pattern to avoid token in exception messages
    # If the request fails, the exception won't contain the full URL with token
    try:
        with httpx.Client(
            base_url="https://api.telegram.org",
            timeout=30,
        ) as client:
            response = client.post(
                f"/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                },
            )
            response.raise_for_status()

            result = response.json()
            if result.get("ok"):
                logger.info("Telegram message sent successfully")
                return True

            logger.error("Telegram API error: %s", result)
            return False

    except httpx.RequestError:
        # BS-3: Log error type only - never log the exception directly
        # as it may contain the URL with the token
        logger.error("Telegram request failed: network error")
        return False
    except httpx.HTTPStatusError as exc:
        # Safe to log status code - no sensitive data
        logger.error("Telegram API error: HTTP %d", exc.response.status_code)
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
