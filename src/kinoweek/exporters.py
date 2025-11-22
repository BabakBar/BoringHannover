"""Export functions for different output formats.

Provides specialized export functions for:
- JSON (enhanced with metadata)
- Markdown (human-readable digest)
- Weekly archives for historical tracking

CSV exports are in the csv_exporters module.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

# Re-export CSV functions for backward compatibility
from kinoweek.csv_exporters import (
    export_concerts_csv,
    export_movies_csv,
    export_movies_grouped_csv,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from kinoweek.models import Event
    from kinoweek.output import GroupedMovie

__all__ = [
    # CSV exports (re-exported)
    "export_movies_csv",
    "export_movies_grouped_csv",
    "export_concerts_csv",
    # JSON/Markdown/Archive exports
    "export_enhanced_json",
    "export_web_json",
    "export_markdown_digest",
    "archive_weekly_data",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================


def _format_duration(minutes: int) -> str:
    """Format duration in minutes to human-readable string."""
    if minutes <= 0:
        return ""
    hours, mins = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h{mins}m" if mins else f"{hours}h"
    return f"{mins}m"


# =============================================================================
# JSON Export (Enhanced)
# =============================================================================


def export_enhanced_json(
    movies: Sequence[Event],
    concerts: Sequence[Event],
    grouped_movies: list[GroupedMovie],
    output_path: Path,
    week_num: int,
    year: int,
) -> None:
    """Export enhanced JSON with all data.

    Args:
        movies: List of movie events.
        concerts: List of concert events.
        grouped_movies: List of grouped movies.
        output_path: Path to output directory.
        week_num: Current week number.
        year: Current year.
    """
    json_path = output_path / "events.json"

    data = {
        "meta": {
            "week": week_num,
            "year": year,
            "generated_at": datetime.now().isoformat(),
            "sources": ["Astor Grand Cinema", "ZAG Arena", "Swiss Life Hall", "Capitol Hannover"],
            "total_movie_showtimes": len(movies),
            "total_unique_films": len(grouped_movies),
            "total_concerts": len(concerts),
        },
        "movies": {
            "unique_films": [
                {
                    "title": m.title,
                    "year": m.year,
                    "duration_min": m.duration_min,
                    "rating": f"FSK{m.rating}" if m.rating else "",
                    "country": m.country,
                    "genres": m.genres,
                    "synopsis": m.synopsis,
                    "poster_url": m.poster_url,
                    "trailer_url": m.trailer_url,
                    "cast": m.cast[:5],  # Limit to top 5
                    "ticket_url": m.ticket_url,
                    "venue": m.venue,
                    "showtimes": [
                        {
                            "date": st.date,
                            "time": st.time,
                            "language": st.language,
                        }
                        for st in m.showtimes
                    ],
                }
                for m in grouped_movies
            ],
            "all_showtimes": [
                {
                    "title": e.title,
                    "date": e.date.isoformat(),
                    "venue": e.venue,
                    "url": e.url,
                    "metadata": dict(e.metadata),
                }
                for e in movies
            ],
        },
        "concerts": [
            {
                "artist": e.title,
                "date": e.date.isoformat(),
                "venue": e.venue,
                "url": e.url,
                "time": e.metadata.get("time", "20:00"),
                "event_type": e.metadata.get("event_type", "concert"),
                "status": e.metadata.get("status", "available"),
                "image_url": e.metadata.get("image_url", ""),
                "address": e.metadata.get("address", ""),
            }
            for e in concerts
        ],
    }

    json_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Exported enhanced JSON to %s", json_path)


# =============================================================================
# Web Frontend JSON Export
# =============================================================================

# Day name abbreviations for frontend
_DAY_ABBREVS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
_GERMAN_DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_GERMAN_MONTHS = ["", "Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def export_web_json(
    movies: Sequence[Event],
    concerts: Sequence[Event],
    output_path: Path,
    week_num: int,
    year: int,
) -> None:
    """Export JSON specifically formatted for the web frontend.

    Creates a structure optimized for the boringhannover frontend:
    - Movies grouped by date with display-ready formatting
    - Concerts with German date formatting
    - All text pre-formatted for display

    Args:
        movies: List of movie events.
        concerts: List of concert events.
        output_path: Path to output directory.
        week_num: Current week number.
        year: Current year.
    """
    json_path = output_path / "web_events.json"

    # Group movies by date
    movies_by_date: dict[str, list[dict]] = {}
    for event in movies:
        date_key = event.date.strftime("%Y-%m-%d")
        if date_key not in movies_by_date:
            movies_by_date[date_key] = []

        # Format language display (JP→DE style)
        language = str(event.metadata.get("language", ""))
        lang_parts = []
        if "Sprache:" in language:
            lang = language.split("Sprache:")[-1].strip().split(",")[0].strip()
            lang_abbrevs = {
                "Englisch": "EN", "Japanisch": "JP", "Deutsch": "DE",
                "Französisch": "FR", "Italienisch": "IT", "Spanisch": "ES",
                "Russisch": "RU", "Koreanisch": "KR", "Chinesisch": "ZH",
            }
            lang_parts.append(lang_abbrevs.get(lang, lang[:2].upper()))
        if "Untertitel:" in language:
            lang_parts.append("DE")  # Subtitles are always German

        lang_display = "→".join(lang_parts) if len(lang_parts) == 2 else (lang_parts[0] if lang_parts else "")

        # Get primary genre (first one if available)
        genres = event.metadata.get("genres", [])
        primary_genre = genres[0] if genres else None

        movies_by_date[date_key].append({
            "title": event.title,
            "year": event.metadata.get("year"),
            "time": event.date.strftime("%H:%M"),
            "duration": _format_duration(int(event.metadata.get("duration", 0))),
            "language": lang_parts[0] if lang_parts else None,
            "subtitles": "DE" if len(lang_parts) == 2 else None,
            "rating": f"FSK{event.metadata.get('rating')}" if event.metadata.get("rating") else None,
            "genre": primary_genre,
            "url": event.url,
        })

    # Convert to frontend format (sorted by date)
    movies_list = []
    for date_key in sorted(movies_by_date.keys()):
        dt = datetime.fromisoformat(date_key)
        movies_list.append({
            "day": _DAY_ABBREVS[dt.weekday()],
            "date": dt.strftime("%d.%m"),
            "movies": sorted(movies_by_date[date_key], key=lambda m: m["time"]),
        })

    # Format concerts
    concerts_list = []
    for event in sorted(concerts, key=lambda e: e.date):
        dt = event.date
        day_name = _GERMAN_DAYS[dt.weekday()]
        month_name = _GERMAN_MONTHS[dt.month]

        # Format date like "29 Nov" or "28 Mar 2026"
        if dt.year != year:
            date_display = f"{dt.day} {month_name} {dt.year}"
        else:
            date_display = f"{dt.day} {month_name}"

        # Extract optional event details
        event_type = event.metadata.get("event_type", "concert")
        genre = event.metadata.get("genre")
        subtitle = event.metadata.get("subtitle")
        status = event.metadata.get("status", "available")

        concerts_list.append({
            "title": event.title,
            "date": date_display,
            "day": day_name,
            "time": event.metadata.get("time", "20:00"),
            "venue": event.venue,
            "url": event.url,
            "eventType": event_type,
            "genre": genre if genre else None,
            "description": subtitle if subtitle else None,
            "status": status,
        })

    # Build final structure
    data = {
        "meta": {
            "week": week_num,
            "year": year,
            "updatedAt": datetime.now().strftime("%a %d %b %H:%M"),
        },
        "movies": movies_list,
        "concerts": concerts_list,
    }

    json_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Exported web frontend JSON to %s", json_path)


# =============================================================================
# Markdown Digest
# =============================================================================


def export_markdown_digest(
    grouped_movies: list[GroupedMovie],
    concerts: Sequence[Event],
    output_path: Path,
    week_num: int,
    year: int,
) -> None:
    """Export a nice markdown digest.

    Args:
        grouped_movies: List of grouped movies.
        concerts: List of concert events.
        output_path: Path to output directory.
        week_num: Current week number.
        year: Current year.
    """
    md_path = output_path / "weekly_digest.md"

    lines = [
        f"# Hannover Week {week_num} ({year})",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "---",
        "",
        "## Movies (Original Version)",
        "",
        f"**{len(grouped_movies)} films** with **{sum(len(m.showtimes) for m in grouped_movies)} showtimes** this week",
        "",
    ]

    # Movies section
    for movie in grouped_movies:
        rating_str = f"FSK{movie.rating}" if movie.rating else ""
        duration_str = _format_duration(movie.duration_min)
        genres_str = ", ".join(movie.genres) if movie.genres else ""

        lines.append(f"### {movie.title} ({movie.year})")
        lines.append("")

        meta_parts = []
        if duration_str:
            meta_parts.append(duration_str)
        if rating_str:
            meta_parts.append(rating_str)
        if movie.country:
            meta_parts.append(movie.country)
        if genres_str:
            meta_parts.append(genres_str)

        if meta_parts:
            lines.append(f"*{' | '.join(meta_parts)}*")
            lines.append("")

        if movie.synopsis:
            synopsis = movie.synopsis[:300] + "..." if len(movie.synopsis) > 300 else movie.synopsis
            lines.append(f"> {synopsis}")
            lines.append("")

        # Showtimes table
        lines.append("| Date | Time | Language |")
        lines.append("|------|------|----------|")
        for st in movie.showtimes:
            lines.append(f"| {st.date} | {st.time} | {st.language} |")
        lines.append("")

        if movie.poster_url:
            lines.append(f"[Poster]({movie.poster_url}) | [Tickets]({movie.ticket_url})")
        else:
            lines.append(f"[Tickets]({movie.ticket_url})")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Concerts section
    lines.extend([
        "## On The Radar",
        "",
        f"**{len(concerts)} upcoming events**",
        "",
        "| Date | Artist | Venue | Status |",
        "|------|--------|-------|--------|",
    ])

    for event in concerts:
        date_str = event.date.strftime("%Y-%m-%d")
        time_str = event.metadata.get("time", "20:00")
        status = event.metadata.get("status", "available")
        status_display = "Available" if status == "available" else "Sold Out"

        lines.append(
            f"| {date_str} {time_str} | [{event.title}]({event.url}) | {event.venue} | {status_display} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Data sourced from Astor Grand Cinema, ZAG Arena, Swiss Life Hall, Capitol Hannover*")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    logger.info("Exported markdown digest to %s", md_path)


# =============================================================================
# Weekly Archive
# =============================================================================


def archive_weekly_data(
    movies: Sequence[Event],
    concerts: Sequence[Event],
    output_path: Path,
    week_num: int,
    year: int,
) -> None:
    """Archive the weekly data snapshot.

    Args:
        movies: List of movie events.
        concerts: List of concert events.
        output_path: Path to output directory.
        week_num: Current week number.
        year: Current year.
    """
    archive_dir = output_path / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_path = archive_dir / f"{year}-W{week_num:02d}.json"

    data = {
        "meta": {
            "week": week_num,
            "year": year,
            "archived_at": datetime.now().isoformat(),
        },
        "movies": [
            {
                "title": e.title,
                "date": e.date.isoformat(),
                "venue": e.venue,
                "url": e.url,
                "metadata": dict(e.metadata),
            }
            for e in movies
        ],
        "concerts": [
            {
                "title": e.title,
                "date": e.date.isoformat(),
                "venue": e.venue,
                "url": e.url,
                "metadata": dict(e.metadata),
            }
            for e in concerts
        ],
    }

    archive_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Archived weekly data to %s", archive_path)
