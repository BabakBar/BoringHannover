"""Output module for BoringHannover with multiple format support.

Provides structured output in various formats through the OutputManager class.
Export implementations are in the exporters module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from boringhannover.constants import BERLIN_TZ
from boringhannover.exporters import (
    archive_weekly_data,
    export_concerts_csv,
    export_enhanced_json,
    export_markdown_digest,
    export_movies_csv,
    export_movies_grouped_csv,
    export_web_json,
)


if TYPE_CHECKING:
    from collections.abc import Sequence

    from boringhannover.models import Event

__all__ = [
    "GroupedMovie",
    "OutputManager",
    "Showtime",
    "export_all_formats",
    "group_movies_by_film",
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
            year = event.metadata.get("year", 0)
            duration = event.metadata.get("duration", 0)
            rating = event.metadata.get("rating", 0)
            genres = event.metadata.get("genres", [])
            cast = event.metadata.get("cast", [])

            films[key] = GroupedMovie(
                title=event.title,
                year=int(year) if isinstance(year, int) else 0,
                duration_min=int(duration) if isinstance(duration, int) else 0,
                rating=int(rating) if isinstance(rating, int) else 0,
                country=str(event.metadata.get("country", "")),
                genres=list(genres) if isinstance(genres, list) else [],
                synopsis=str(event.metadata.get("synopsis", "")),
                poster_url=str(event.metadata.get("poster_url", "")),
                trailer_url=str(event.metadata.get("trailer_url", "")),
                cast=list(cast) if isinstance(cast, list) else [],
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
# Output Manager
# =============================================================================


class OutputManager:
    """Manages all output formats for BoringHannover."""

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
        now = datetime.now(BERLIN_TZ)
        week_num = now.isocalendar()[1]
        year = now.year

        # Group movies by film
        grouped_movies = group_movies_by_film(movies)

        # Export all formats
        export_movies_csv(movies, self.output_path, week_num)
        export_movies_grouped_csv(grouped_movies, self.output_path, week_num)
        export_concerts_csv(concerts, self.output_path, week_num)
        export_enhanced_json(
            movies, concerts, grouped_movies, self.output_path, week_num, year
        )
        export_web_json(movies, concerts, self.output_path, week_num, year)
        export_markdown_digest(
            grouped_movies, concerts, self.output_path, week_num, year
        )
        archive_weekly_data(movies, concerts, self.output_path, week_num, year)

        return {
            "movies_csv": self.output_path / "movies.csv",
            "movies_grouped_csv": self.output_path / "movies_grouped.csv",
            "concerts_csv": self.output_path / "concerts.csv",
            "json": self.output_path / "events.json",
            "web_json": self.output_path / "web_events.json",
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
