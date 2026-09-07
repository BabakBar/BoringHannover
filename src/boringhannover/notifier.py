"""Notification module for message formatting and delivery.

Formats events into a structured message with two sections:
1. "Movies" - OV movies at Astor Cinema
2. "On The Radar" - Big upcoming concerts and events
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NotRequired, TypedDict

from boringhannover.constants import BERLIN_TZ
from boringhannover.formatting import format_movies_section, format_radar_section
from boringhannover.occasions import OccasionBundle, build_occasion_bundles
from boringhannover.output import export_all_formats


if TYPE_CHECKING:
    from boringhannover.models import Event
    from boringhannover.occasions import OccasionDefinition


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
    city_occasions: NotRequired[list[OccasionDefinition]]


# =============================================================================
# Message Formatting
# =============================================================================


def _format_occasions_section(bundles: list[OccasionBundle]) -> str:
    """Format compact occasion summaries without dumping their programmes."""
    lines = ["*Special in Hannover*"]
    for bundle in bundles:
        definition = bundle.definition
        date_range = (
            f"{definition.start_date.strftime('%d %b')}"
            f"-{definition.end_date.strftime('%d %b')}"
        )
        lines.extend(
            [
                f"  *{definition.name}*",
                f"  {date_range} · {len(bundle.events)} programme items",
                f"  {definition.source_url}",
            ]
        )
    return "\n".join(lines)


def format_message(
    events_data: EventsData,
    *,
    now: datetime | None = None,
) -> str:
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
    occasion_definitions = events_data.get("city_occasions", [])
    current = now or datetime.now(BERLIN_TZ)
    regular_radar, occasion_bundles = build_occasion_bundles(
        radar,
        occasion_definitions=occasion_definitions,
        now=current,
    )

    week_num = current.isocalendar()[1]
    lines: list[str] = [f"*Hannover Week {week_num}*\n"]

    # Section 1: Movies
    lines.append(format_movies_section(movies))
    lines.append("")

    if occasion_bundles:
        lines.append(_format_occasions_section(occasion_bundles))
        lines.append("")

    # Section 2: Radar (Concerts)
    lines.append(format_radar_section(regular_radar))

    return "\n".join(lines).strip()


# =============================================================================
# File Output
# =============================================================================


def save_to_file(
    message: str,
    output_dir: str | Path = "output",
) -> None:
    """Save the human-readable digest message to a local file.

    Args:
        message: Formatted message string.
        output_dir: Output directory path.
    """
    output_path = Path(output_dir)

    try:
        output_path.mkdir(parents=True, exist_ok=True)

        # Save formatted message
        message_file = output_path / "latest_message.txt"
        message_file.write_text(message, encoding="utf-8")

        logger.info("Message saved to %s", message_file)

    except OSError:
        logger.exception("Failed to save message")


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
    occasions = events_data.get("city_occasions", [])

    return export_all_formats(
        movies,
        concerts,
        output_dir,
        occasion_definitions=occasions,
    )


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
        save_to_file(message)

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
