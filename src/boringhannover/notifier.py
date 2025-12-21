"""Notification module for message formatting and delivery.

Formats events into a structured message with two sections:
1. "Movies (This Week)" - OV movies at Astor Cinema
2. "On The Radar" - Big upcoming concerts and events
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from boringhannover.constants import BERLIN_TZ
from boringhannover.formatting import format_movies_section, format_radar_section
from boringhannover.output import export_all_formats


if TYPE_CHECKING:
    from boringhannover.models import Event


__all__ = [
    "format_message",
    "notify",
    "save_all_formats",
    "save_to_file",
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
    """Format events into a structured message.

    Creates a two-section message with movies and upcoming concerts,
    formatted with Markdown.

    Args:
        events_data: Dictionary with categorized event lists.

    Returns:
        Formatted message string.
    """
    movies = events_data.get("movies_this_week", [])
    radar = events_data.get("big_events_radar", [])

    week_num = datetime.now(BERLIN_TZ).isocalendar()[1]
    lines: list[str] = [f"*Hannover Week {week_num}*\n"]

    # Section 1: Movies
    lines.append(format_movies_section(movies))
    lines.append("")

    # Section 2: Radar (Concerts)
    lines.append(format_radar_section(radar))

    return "\n".join(lines).strip()


# =============================================================================
# File Output
# =============================================================================


def _event_to_dict(event: Event) -> dict[str, Any]:
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
        "metadata": dict(event.metadata) if event.metadata else {},
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
                _event_to_dict(e) for e in events_data.get("movies_this_week", [])
            ],
            "big_events_radar": [
                _event_to_dict(e) for e in events_data.get("big_events_radar", [])
            ],
        }

        json_file = output_path / "events.json"
        json_file.write_text(
            json.dumps(json_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info("Results saved to %s/", output_path)

    except OSError:
        logger.exception("Failed to save results")


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


def notify(events_data: EventsData) -> bool:
    """Save event data to local files.

    Creates output files in the specified directory with event data
    in multiple formats (CSV, JSON, Markdown, Archive).

    Args:
        events_data: Dictionary of categorized event lists.

    Returns:
        True if save was successful.
    """
    try:
        message = format_message(events_data)

        # Save formatted message
        save_to_file(message, events_data)

        # Export all formats (CSV, Markdown, Archive)
        output_paths = save_all_formats(events_data)

        logger.info("Results saved successfully")
        logger.info("Message:\n%s", message)
        logger.info("Output files:")
        for fmt, path in output_paths.items():
            logger.info("  - %s: %s", fmt, path)

    except Exception:
        logger.exception("Notification failed")
        return False
    else:
        return True
