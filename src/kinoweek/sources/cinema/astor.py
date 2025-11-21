"""Astor Grand Cinema Hannover source.

Fetches OV (original version) movie showtimes via the cinema's JSON API.
Filters out German-dubbed versions to only include original language films.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, ClassVar

from kinoweek.config import ASTOR_API_URL
from kinoweek.models import Event
from kinoweek.sources.base import (
    BaseSource,
    create_http_client,
    is_original_version,
    register_source,
)

__all__ = ["AstorSource"]

logger = logging.getLogger(__name__)


@register_source("astor_hannover")
class AstorSource(BaseSource):
    """Scraper for Astor Grand Cinema Hannover.

    Fetches OV (original version) movie showtimes via the cinema's JSON API.
    Filters out German-dubbed versions to only include original language films.

    API Endpoint: https://backend.premiumkino.de/v1/de/hannover/program

    Attributes:
        source_name: "Astor Grand Cinema"
        source_type: "cinema"
    """

    source_name: ClassVar[str] = "Astor Grand Cinema"
    source_type: ClassVar[str] = "cinema"

    # Configuration
    API_URL: ClassVar[str] = ASTOR_API_URL
    BASE_TICKET_URL: ClassVar[str] = "https://hannover.premiumkino.de/film/"

    def fetch(self) -> list[Event]:
        """Fetch OV movie showtimes from Astor API.

        Returns:
            List of Event objects with category="movie".

        Raises:
            httpx.RequestError: If the API request fails.
        """
        logger.info("Fetching movies from %s", self.source_name)

        with create_http_client() as client:
            client.headers.update(
                {
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json; charset=utf-8",
                    "Referer": "https://hannover.premiumkino.de/",
                }
            )
            response = client.get(self.API_URL)
            response.raise_for_status()
            data = response.json()

        events = self._parse_response(data)
        logger.info("Found %d OV movie showtimes", len(events))
        return events

    def _parse_response(self, data: dict[str, Any]) -> list[Event]:
        """Parse the Astor API response into Event objects.

        Args:
            data: JSON response from the API.

        Returns:
            List of parsed Event objects.
        """
        events: list[Event] = []

        # Build lookup tables
        genres_map = {g["id"]: g["name"] for g in data.get("genres", [])}
        movies_map = {m["id"]: m for m in data.get("movies", [])}

        for performance in data.get("performances", []):
            event = self._parse_performance(performance, movies_map, genres_map)
            if event:
                events.append(event)

        return events

    def _parse_performance(
        self,
        performance: dict[str, Any],
        movies_map: dict[int, dict[str, Any]],
        genres_map: dict[int, str],
    ) -> Event | None:
        """Parse a single performance into an Event.

        Args:
            performance: Performance data from API.
            movies_map: Movie ID to movie data mapping.
            genres_map: Genre ID to genre name mapping.

        Returns:
            Parsed Event or None if skipped (e.g., German dub).
        """
        movie_id = performance.get("movieId")
        if movie_id not in movies_map:
            return None

        movie = movies_map[movie_id]
        title = movie.get("name", "Unknown")
        language = performance.get("language", "")

        # Filter for Original Version only
        if not is_original_version(language):
            logger.debug("Skipping non-OV: %s (%s)", title, language)
            return None

        begin_str = performance.get("begin")
        if not begin_str:
            return None

        # Extract metadata
        metadata = self._extract_metadata(movie, performance, genres_map)
        metadata["movie_id"] = movie_id

        # Build ticket URL with movie slug
        slug = movie.get("slug", "")
        ticket_url = (
            f"{self.BASE_TICKET_URL}{slug}" if slug else "https://hannover.premiumkino.de/"
        )

        return Event(
            title=title,
            date=datetime.fromisoformat(begin_str),
            venue=self.source_name,
            url=ticket_url,
            category="movie",
            metadata=metadata,
        )

    def _extract_metadata(
        self,
        movie: dict[str, Any],
        performance: dict[str, Any],
        genres_map: dict[int, str],
    ) -> dict[str, Any]:
        """Extract rich metadata from movie and performance data.

        Args:
            movie: Movie data from API.
            performance: Performance data from API.
            genres_map: Genre ID to genre name mapping.

        Returns:
            Dictionary with extracted metadata.
        """
        # Extract genres properly (filter empty strings)
        genre_names = [
            genres_map.get(gid, "") for gid in movie.get("genreIds", [])
        ]
        genre_names = [g for g in genre_names if g]

        # Extract poster URL if available
        poster = movie.get("poster", {})
        poster_url = poster.get("src", "") if isinstance(poster, dict) else ""

        # Extract synopsis from translations
        synopsis = self._extract_synopsis(movie.get("translations", []))

        # Extract trailer URL (prefer 720p)
        trailer_url = self._extract_trailer_url(movie.get("trailers", []))

        # Extract cast (directors and main actors)
        cast = [
            {"role": person.get("function", ""), "name": person.get("name", "")}
            for person in movie.get("casts", [])
        ]

        return {
            "duration": movie.get("minutes", 0),
            "rating": movie.get("rating", 0),
            "year": movie.get("year", 0),
            "country": movie.get("country", ""),
            "genres": genre_names,
            "language": performance.get("language", ""),
            "poster_url": poster_url,
            "synopsis": synopsis,
            "trailer_url": trailer_url,
            "cast": cast,
        }

    @staticmethod
    def _extract_synopsis(translations: list[dict[str, Any]]) -> str:
        """Extract synopsis from translations, preferring German.

        Args:
            translations: List of translation objects.

        Returns:
            Synopsis string or empty string if not found.
        """
        if not translations:
            return ""

        # Prefer German, fall back to any available
        for trans in translations:
            if trans.get("language") == "de":
                desc = trans.get("descShort") or trans.get("descLong") or ""
                return str(desc)

        # Fallback to first available
        desc = translations[0].get("descShort") or translations[0].get("descLong") or ""
        return str(desc)

    @staticmethod
    def _extract_trailer_url(trailers: list[dict[str, Any]]) -> str:
        """Extract best quality trailer URL.

        Args:
            trailers: List of trailer objects.

        Returns:
            Trailer URL or empty string if not found.
        """
        for trailer in trailers:
            if trailer.get("url720"):
                return str(trailer["url720"])
            if trailer.get("url1080"):
                return str(trailer["url1080"])
        return ""
