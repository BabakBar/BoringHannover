"""Output module for KinoWeek with multiple format support.

Provides structured output in various formats:
- JSON (enhanced with metadata)
- CSV (flat tables for movies and concerts)
- Markdown (human-readable digest)
- Weekly archives for historical tracking
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from kinoweek.models import Event

__all__ = [
    "OutputManager",
    "GroupedMovie",
    "group_movies_by_film",
    "export_all_formats",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class Showtime:
    """A single showtime for a movie."""

    date: str
    time: str
    language: str
    has_subtitles: bool = False


@dataclass
class GroupedMovie:
    """A movie with all its showtimes grouped together."""

    title: str
    year: int
    duration_min: int
    rating: int
    country: str
    genres: list[str]
    synopsis: str
    poster_url: str
    trailer_url: str
    cast: list[dict[str, str]]
    ticket_url: str
    venue: str
    showtimes: list[Showtime] = field(default_factory=list)
    movie_id: str = ""


# =============================================================================
# Movie Grouping
# =============================================================================


def group_movies_by_film(movies: Sequence[Event]) -> list[GroupedMovie]:
    """Group movie showtimes by unique film.

    Args:
        movies: List of movie events (each representing one showtime).

    Returns:
        List of GroupedMovie objects with consolidated showtimes.
    """
    films: dict[str, GroupedMovie] = {}

    for event in movies:
        # Create unique key based on title and year
        key = f"{event.title}_{event.metadata.get('year', 0)}"

        if key not in films:
            films[key] = GroupedMovie(
                title=event.title,
                year=int(event.metadata.get("year", 0)),
                duration_min=int(event.metadata.get("duration", 0)),
                rating=int(event.metadata.get("rating", 0)),
                country=str(event.metadata.get("country", "")),
                genres=list(event.metadata.get("genres", [])),
                synopsis=str(event.metadata.get("synopsis", "")),
                poster_url=str(event.metadata.get("poster_url", "")),
                trailer_url=str(event.metadata.get("trailer_url", "")),
                cast=list(event.metadata.get("cast", [])),
                ticket_url=event.url,
                venue=event.venue,
                movie_id=str(event.metadata.get("movie_id", "")),
            )

        # Parse language info
        language = str(event.metadata.get("language", ""))
        has_subtitles = "Untertitel:" in language

        # Abbreviate language
        lang_short = language
        for full, abbrev in [
            ("Sprache: ", ""),
            ("Untertitel: ", "UT:"),
            ("Englisch", "EN"),
            ("Japanisch", "JP"),
            ("Deutsch", "DE"),
            ("Französisch", "FR"),
            ("Italienisch", "IT"),
            ("Spanisch", "ES"),
        ]:
            lang_short = lang_short.replace(full, abbrev)

        films[key].showtimes.append(
            Showtime(
                date=event.date.strftime("%Y-%m-%d"),
                time=event.date.strftime("%H:%M"),
                language=lang_short,
                has_subtitles=has_subtitles,
            )
        )

    # Sort films by first showtime
    result = list(films.values())
    result.sort(key=lambda m: m.showtimes[0].date if m.showtimes else "")

    return result


# =============================================================================
# CSV Export
# =============================================================================


def _export_movies_csv(
    movies: Sequence[Event],
    output_path: Path,
    week_num: int,
) -> None:
    """Export movies to CSV file.

    Args:
        movies: List of movie events.
        output_path: Path to output directory.
        week_num: Current week number.
    """
    csv_path = output_path / "movies.csv"

    fieldnames = [
        "week",
        "title",
        "date",
        "time",
        "duration_min",
        "rating",
        "year",
        "country",
        "language",
        "genres",
        "poster_url",
        "ticket_url",
        "venue",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for event in movies:
            genres = event.metadata.get("genres", [])
            writer.writerow({
                "week": week_num,
                "title": event.title,
                "date": event.date.strftime("%Y-%m-%d"),
                "time": event.date.strftime("%H:%M"),
                "duration_min": event.metadata.get("duration", 0),
                "rating": event.metadata.get("rating", 0),
                "year": event.metadata.get("year", 0),
                "country": event.metadata.get("country", ""),
                "language": event.metadata.get("language", ""),
                "genres": "; ".join(genres) if genres else "",
                "poster_url": event.metadata.get("poster_url", ""),
                "ticket_url": event.url,
                "venue": event.venue,
            })

    logger.info("Exported %d movie showtimes to %s", len(movies), csv_path)


def _export_movies_grouped_csv(
    grouped_movies: list[GroupedMovie],
    output_path: Path,
    week_num: int,
) -> None:
    """Export grouped movies to CSV file.

    Args:
        grouped_movies: List of grouped movies.
        output_path: Path to output directory.
        week_num: Current week number.
    """
    csv_path = output_path / "movies_grouped.csv"

    fieldnames = [
        "week",
        "title",
        "year",
        "duration_min",
        "rating",
        "country",
        "genres",
        "num_showtimes",
        "showtimes",
        "poster_url",
        "trailer_url",
        "ticket_url",
        "synopsis",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for movie in grouped_movies:
            # Format showtimes as compact string
            showtimes_str = "; ".join(
                f"{st.date} {st.time} ({st.language})"
                for st in movie.showtimes
            )

            writer.writerow({
                "week": week_num,
                "title": movie.title,
                "year": movie.year,
                "duration_min": movie.duration_min,
                "rating": movie.rating,
                "country": movie.country,
                "genres": "; ".join(movie.genres),
                "num_showtimes": len(movie.showtimes),
                "showtimes": showtimes_str,
                "poster_url": movie.poster_url,
                "trailer_url": movie.trailer_url,
                "ticket_url": movie.ticket_url,
                "synopsis": movie.synopsis[:200] + "..." if len(movie.synopsis) > 200 else movie.synopsis,
            })

    logger.info("Exported %d unique films to %s", len(grouped_movies), csv_path)


def _export_concerts_csv(
    concerts: Sequence[Event],
    output_path: Path,
    week_num: int,
) -> None:
    """Export concerts to CSV file.

    Args:
        concerts: List of concert events.
        output_path: Path to output directory.
        week_num: Current week number.
    """
    csv_path = output_path / "concerts.csv"

    fieldnames = [
        "week",
        "artist",
        "date",
        "time",
        "venue",
        "event_type",
        "status",
        "ticket_url",
        "image_url",
        "address",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for event in concerts:
            writer.writerow({
                "week": week_num,
                "artist": event.title,
                "date": event.date.strftime("%Y-%m-%d"),
                "time": event.metadata.get("time", "20:00"),
                "venue": event.venue,
                "event_type": event.metadata.get("event_type", "concert"),
                "status": event.metadata.get("status", "available"),
                "ticket_url": event.url,
                "image_url": event.metadata.get("image_url", ""),
                "address": event.metadata.get("address", ""),
            })

    logger.info("Exported %d concerts to %s", len(concerts), csv_path)


# =============================================================================
# JSON Export (Enhanced)
# =============================================================================


def _export_enhanced_json(
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
# Markdown Digest
# =============================================================================


def _format_duration(minutes: int) -> str:
    """Format duration in minutes to human-readable string."""
    if minutes <= 0:
        return ""
    hours, mins = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h{mins}m" if mins else f"{hours}h"
    return f"{mins}m"


def _export_markdown_digest(
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
        "## 🎬 Movies (Original Version)",
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
        "## 🎵 On The Radar",
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
        status_emoji = "✅" if status == "available" else "❌ Sold Out"

        lines.append(
            f"| {date_str} {time_str} | [{event.title}]({event.url}) | {event.venue} | {status_emoji} |"
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


def _archive_weekly_data(
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


# =============================================================================
# Main Export Function
# =============================================================================


class OutputManager:
    """Manages all output formats for KinoWeek."""

    def __init__(self, output_dir: str | Path = "output") -> None:
        """Initialize output manager.

        Args:
            output_dir: Base directory for output files.
        """
        self.output_path = Path(output_dir)
        self.output_path.mkdir(parents=True, exist_ok=True)

    def export_all(
        self,
        movies: Sequence[Event],
        concerts: Sequence[Event],
    ) -> dict[str, Path]:
        """Export all output formats.

        Args:
            movies: List of movie events.
            concerts: List of concert events.

        Returns:
            Dictionary mapping format names to output paths.
        """
        now = datetime.now()
        week_num = now.isocalendar()[1]
        year = now.year

        # Group movies by film
        grouped_movies = group_movies_by_film(movies)

        # Export all formats
        _export_movies_csv(movies, self.output_path, week_num)
        _export_movies_grouped_csv(grouped_movies, self.output_path, week_num)
        _export_concerts_csv(concerts, self.output_path, week_num)
        _export_enhanced_json(movies, concerts, grouped_movies, self.output_path, week_num, year)
        _export_markdown_digest(grouped_movies, concerts, self.output_path, week_num, year)
        _archive_weekly_data(movies, concerts, self.output_path, week_num, year)

        return {
            "movies_csv": self.output_path / "movies.csv",
            "movies_grouped_csv": self.output_path / "movies_grouped.csv",
            "concerts_csv": self.output_path / "concerts.csv",
            "json": self.output_path / "events.json",
            "markdown": self.output_path / "weekly_digest.md",
            "archive": self.output_path / "archive" / f"{year}-W{week_num:02d}.json",
        }


def export_all_formats(
    movies: Sequence[Event],
    concerts: Sequence[Event],
    output_dir: str | Path = "output",
) -> dict[str, Path]:
    """Convenience function to export all formats.

    Args:
        movies: List of movie events.
        concerts: List of concert events.
        output_dir: Base directory for output files.

    Returns:
        Dictionary mapping format names to output paths.
    """
    manager = OutputManager(output_dir)
    return manager.export_all(movies, concerts)
