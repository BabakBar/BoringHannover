"""Béi Chéz Heinz Hannover source.

Fetches upcoming concerts from Béi Chéz Heinz - Hannover's legendary
basement club in the Linden district. Known for punk, indie, metal, and
alternative music since 1990.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from bs4 import BeautifulSoup


if TYPE_CHECKING:
    from bs4 import Tag

from boringhannover.config import GERMAN_MONTH_MAP
from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sources.base import (
    BaseSource,
    create_http_client,
    register_source,
)


__all__ = ["BeiChezHeinzSource"]

logger = logging.getLogger(__name__)


@register_source("bei_chez_heinz")
class BeiChezHeinzSource(BaseSource):
    """Scraper for Béi Chéz Heinz Hannover.

    Fetches upcoming concerts from the legendary basement club.
    Filters for "_Konzert_" category to focus on live music.

    Website: https://www.beichezheinz.de/programm

    Attributes:
        source_name: "Béi Chéz Heinz"
        source_type: "concert"
    """

    source_name: ClassVar[str] = "Béi Chéz Heinz"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 20

    # Configuration
    URL: ClassVar[str] = "https://www.beichezheinz.de/programm"
    BASE_URL: ClassVar[str] = "https://www.beichezheinz.de"
    ADDRESS: ClassVar[str] = "Liepmannstraße 7b, 30453 Hannover"

    # Categories: Konzert, Party & Disco, Spiel & Spaß, Kleinkunst
    CONCERT_CATEGORY: ClassVar[str] = "Konzert"

    def fetch(self) -> list[Event]:
        """Fetch concert events from Béi Chéz Heinz.

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
        """Parse all concert events from the page.

        Args:
            soup: Parsed HTML document.

        Returns:
            List of parsed Event objects (concerts only).
        """
        events: list[Event] = []

        # Events are in div.pane containers
        event_panes = soup.find_all("div", class_="pane")

        for pane in event_panes:
            # Check if this pane has a title (h3)
            title_elem = pane.find("h3")
            if not title_elem:
                continue

            # Check category - only process concerts
            category_elem = pane.find("h4")
            if not category_elem:
                continue

            category_text = category_elem.get_text(strip=True)
            if self.CONCERT_CATEGORY not in category_text:
                continue

            event = self._parse_event(pane)
            if event:
                events.append(event)
                if self.max_events and len(events) >= self.max_events:
                    break

        return events

    def _parse_event(self, pane: Tag) -> Event | None:
        """Parse a single event from a pane div.

        Args:
            pane: BeautifulSoup Tag element (div.pane).

        Returns:
            Parsed Event or None if parsing fails.
        """
        try:
            # Extract title from h3
            title_elem = pane.find("h3")
            if not title_elem:
                return None

            # Get title text, prefer link text if available
            title_link = title_elem.find("a")
            if title_link:
                title = title_link.get_text(strip=True)
                href = title_link.get("href", "")
            else:
                title = title_elem.get_text(strip=True)
                href = ""

            if not title:
                return None

            # Build event URL - href format: programm/YYYY-MM-DD/ID
            if href and not href.startswith("http"):
                event_url = f"{self.BASE_URL}/{href}"
            else:
                event_url = href or self.URL

            # Extract date from URL first (most reliable)
            event_date = self._parse_date_from_url(href)

            # Get info section for time and price
            info_elem = pane.find("div", class_="bch-event-info")
            info_text = (
                info_elem.get_text(separator=" | ", strip=True) if info_elem else ""
            )

            # Parse time from info text
            time_str = "20:00"
            if info_text:
                event_date, time_str = self._parse_date_time(info_text, event_date)

            if not event_date:
                return None

            # Extract price info
            price = self._extract_price(info_text)

            # Extract genre from title if present (e.g., "FREUDE (Alternative / Österreich)")
            genre = self._extract_genre(title)

            return Event(
                title=title,
                date=event_date,
                venue=self.source_name,
                url=event_url,
                category="radar",
                metadata={
                    "time": time_str,
                    "price": price,
                    "genre": genre,
                    "event_type": "concert",
                    "address": self.ADDRESS,
                },
            )

        except Exception as exc:
            logger.debug("Error parsing %s event: %s", self.source_name, exc)
            return None

    def _parse_date_time(
        self, text: str, existing_date: datetime | None = None
    ) -> tuple[datetime | None, str]:
        """Parse date and time from event text.

        Handles formats like:
        - "Samstag 22. November 2025"
        - "Einlass: 19.00 Uhr" / "Beginn: 20.00 Uhr"

        Args:
            text: Full text content of the event item.
            existing_date: Optional date already parsed from URL.

        Returns:
            Tuple of (datetime, time_string).
        """
        event_date = existing_date
        time_str = "20:00"

        # Parse date if not provided: "Samstag 22. November 2025" or "22. November 2025"
        if not event_date:
            date_pattern = r"(\d{1,2})\.\s*(\w+)\s*(\d{4})"
            date_match = re.search(date_pattern, text)
            if date_match:
                day = int(date_match.group(1))
                month_str = date_match.group(2).lower()
                year = int(date_match.group(3))

                month = GERMAN_MONTH_MAP.get(month_str, 0)
                if month:
                    try:
                        event_date = datetime(year, month, day, 20, 0, tzinfo=BERLIN_TZ)
                    except ValueError:
                        pass

        # Parse time: prefer "Beginn:" over "Einlass:"
        beginn_match = re.search(r"Beginn[:\s]*(\d{1,2})[.\:](\d{2})", text)
        if beginn_match:
            hour, minute = beginn_match.groups()
            time_str = f"{int(hour)}:{minute}"
            if event_date:
                event_date = event_date.replace(hour=int(hour), minute=int(minute))
        else:
            # Fallback to Einlass time
            einlass_match = re.search(r"Einlass[:\s]*(\d{1,2})[.\:](\d{2})", text)
            if einlass_match:
                hour, minute = einlass_match.groups()
                # Concerts typically start 1 hour after doors
                start_hour = min(int(hour) + 1, 23)
                time_str = f"{start_hour}:{minute}"
                if event_date:
                    event_date = event_date.replace(hour=start_hour, minute=int(minute))

        return event_date, time_str

    def _parse_date_from_url(self, href: str) -> datetime | None:
        """Extract date from URL pattern.

        URL format: /programm/2025-11-22/...

        Args:
            href: Event URL path.

        Returns:
            Parsed datetime or None.
        """
        match = re.search(r"/(\d{4})-(\d{2})-(\d{2})", href)
        if not match:
            return None

        try:
            year, month, day = match.groups()
            return datetime(int(year), int(month), int(day), 20, 0, tzinfo=BERLIN_TZ)
        except (ValueError, TypeError):
            return None

    def _extract_price(self, text: str) -> str:
        """Extract price information from event text.

        Args:
            text: Full text content.

        Returns:
            Price string or empty string.
        """
        # Look for "Abendkasse:" or price patterns
        price_patterns = [
            r"Abendkasse[:\s]*([^|]+)",
            r"(\d+[,.]?\d*\s*€)",
            r"(Eintritt frei)",
            r"(Ein Hut geht rum)",
        ]

        for pattern in price_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return ""

    def _extract_genre(self, title: str) -> str:
        """Extract genre from title if present in parentheses.

        Example: "FREUDE (Alternative / Österreich)" -> "Alternative"

        Args:
            title: Event title.

        Returns:
            Genre string or empty string.
        """
        match = re.search(r"\(([^)]+)\)", title)
        if match:
            genre_text = match.group(1)
            # Take first part before "/" or ","
            genre = re.split(r"[/,]", genre_text)[0].strip()
            return genre
        return ""
