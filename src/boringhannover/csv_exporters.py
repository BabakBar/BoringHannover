"""CSV export functions for BoringHannover.

Provides CSV export for movies, grouped movies, and concerts.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from boringhannover.models import Event
    from boringhannover.output import GroupedMovie

__all__ = [
    "export_movies_csv",
    "export_movies_grouped_csv",
    "export_concerts_csv",
]

logger = logging.getLogger(__name__)


def export_movies_csv(
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


def export_movies_grouped_csv(
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


def export_concerts_csv(
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
