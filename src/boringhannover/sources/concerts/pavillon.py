"""Pavillon Hannover source.

Fetches upcoming concerts from Kulturzentrum Pavillon - one of
Germany's oldest sociocultural centers with 350+ events per year.
Focuses on world music, jazz, and international artists.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sources.base import BaseSource, create_http_client, register_source


__all__ = ["PavillonSource"]

logger = logging.getLogger(__name__)


@register_source("pavillon")
class PavillonSource(BaseSource):
    """Scraper for Kulturzentrum Pavillon Hannover.

    Fetches upcoming concerts from the venue's program page.
    Filters for "Konzert" category to focus on live music.

    Website: https://pavillon-hannover.de/programm

    Attributes:
        source_name: "Pavillon"
        source_type: "concert"
    """

    source_name: ClassVar[str] = "Pavillon"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 20

    # Configuration
    URL: ClassVar[str] = "https://pavillon-hannover.de/programm"
    BASE_URL: ClassVar[str] = "https://pavillon-hannover.de"
    ADDRESS: ClassVar[str] = "Lister Meile 4, 30161 Hannover"

    # Categories to include (music-related)
    CONCERT_CATEGORIES: ClassVar[tuple[str, ...]] = ("Konzert", "Festival", "Party")

    def fetch(self) -> list[Event]:
        """Fetch concert events from Pavillon Hannover.

        Returns:
            List of Event objects with category="radar".

        Raises:
            httpx.RequestError: If the HTTP request fails.
        """
        logger.info("Fetching concerts from %s", self.source_name)

        with create_http_client() as client:
            response = client.get(self.URL)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

        events = self._parse_events(soup)
        logger.info("Found %d events from %s", len(events), self.source_name)
        return events

    def _parse_events(self, soup: BeautifulSoup) -> list[Event]:
        """Parse concert events from the program page.

        Args:
            soup: Parsed HTML document.

        Returns:
            List of parsed Event objects (concerts only).
        """
        events: list[Event] = []
        seen_urls: set[str] = set()

        # Find all event detail links
        event_links = soup.select('a[href*="/event/details/"]')

        for link in event_links:
            href_raw = link.get("href", "")
            href = str(href_raw) if href_raw else ""
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)

            # Get parent container with event info
            event_text = self._get_event_text(link)
            if not event_text:
                continue

            # Check if this is a concert
            if not self._is_concert(event_text):
                continue

            # Skip cancelled/postponed events
            if self._is_cancelled(event_text):
                continue

            event = self._parse_event(href, event_text)
            if event:
                events.append(event)
                if self.max_events and len(events) >= self.max_events:
                    break

        return events

    def _get_event_text(self, link: Tag) -> str:
        """Get the full text content of an event's container.

        Args:
            link: BeautifulSoup anchor element.

        Returns:
            Event text content or empty string.
        """
        # Walk up to find container with date info
        parent = link.parent
        for _ in range(6):
            if not parent:
                break
            text = str(parent.get_text(separator=" | ", strip=True))
            # Check if this contains event info (date pattern)
            if re.search(r"\d{1,2}\.\d{1,2}\.\d{4}", text):
                return text
            parent = parent.parent
        return ""

    def _is_concert(self, text: str) -> bool:
        """Check if event is a concert.

        Args:
            text: Event text content.

        Returns:
            True if event is music-related.
        """
        return any(cat in text for cat in self.CONCERT_CATEGORIES)

    def _is_cancelled(self, text: str) -> bool:
        """Check if event is cancelled or postponed.

        Args:
            text: Event text content.

        Returns:
            True if event should be skipped.
        """
        skip_patterns = [
            "Entfällt",
            "Wird Verschoben",
            "Abgesagt",
            "Cancelled",
        ]
        return any(pattern.lower() in text.lower() for pattern in skip_patterns)

    def _parse_event(self, href: str, text: str) -> Event | None:
        """Parse event details from URL and text content.

        Args:
            href: Event detail URL path.
            text: Event text content.

        Returns:
            Parsed Event or None if parsing fails.
        """
        try:
            # Build full URL
            event_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

            # Parse date and time from text
            # Format: "Sa | 22.11.2025 | 18:30 Uhr"  # noqa: ERA001
            event_date, time_str = self._parse_date_time(text)
            if not event_date:
                return None

            # Extract title - usually after time, before "Tickets"
            title = self._extract_title(text)
            if not title:
                return None

            # Extract category
            category = self._extract_category(text)

            return Event(
                title=title,
                date=event_date,
                venue=self.source_name,
                url=event_url,
                category="radar",
                metadata={
                    "time": time_str,
                    "genre": category,
                    "event_type": "concert",
                    "address": self.ADDRESS,
                },
            )

        except Exception as exc:
            logger.debug("Error parsing %s event: %s", self.source_name, exc)
            return None

    def _parse_date_time(self, text: str) -> tuple[datetime | None, str]:
        """Parse date and time from event text.

        Format: "Sa | 22.11.2025 | 18:30 Uhr"

        Args:
            text: Event text content.

        Returns:
            Tuple of (datetime, time_string).
        """
        event_date = None
        time_str = "20:00"

        # Extract date: DD.MM.YYYY
        date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
        if date_match:
            day, month, year = date_match.groups()
            from contextlib import suppress  # noqa: PLC0415

            with suppress(ValueError):
                event_date = datetime(
                    int(year), int(month), int(day), 20, 0, tzinfo=BERLIN_TZ
                )

        # Extract time: HH:MM Uhr
        time_match = re.search(r"(\d{1,2}):(\d{2})\s*Uhr", text)
        if time_match:
            hour, minute = time_match.groups()
            time_str = f"{int(hour)}:{minute}"
            if event_date:
                event_date = event_date.replace(hour=int(hour), minute=int(minute))

        return event_date, time_str

    def _extract_title(self, text: str) -> str:
        """Extract event title from text.

        Title is usually the prominent text after date/time info.

        Args:
            text: Event text content.

        Returns:
            Event title or empty string.
        """
        # Remove common prefixes and split by |
        parts = text.split("|")

        # Find the part that looks like a title (after Uhr, before Tickets)
        title_candidates = []
        found_time = False

        for raw_part in parts:
            part = raw_part.strip()
            if "Uhr" in part:
                found_time = True
                continue
            if found_time and part and part != "Tickets":
                # Skip category names
                if part in (
                    "Konzert",
                    "Festival",
                    "Party",
                    "Lesung",
                    "Comedy",
                    "Börse",
                ):
                    continue
                # Skip dates and short items
                if re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", part):
                    continue
                if len(part) < 3:
                    continue
                title_candidates.append(part)

        # First substantial candidate is usually the title
        if title_candidates:
            return title_candidates[0]

        return ""

    def _extract_category(self, text: str) -> str:
        """Extract event category from text.

        Args:
            text: Event text content.

        Returns:
            Category string.
        """
        for cat in self.CONCERT_CATEGORIES:
            if cat in text:
                return cat
        return "Konzert"
