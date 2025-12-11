"""Kulturzentrum Faust Hannover source.

Fetches upcoming events from Kulturzentrum Faust including:
- Livemusik (concerts, live music)
- Party (club nights, DJ events)
- Bühne (theater, comedy - English language only)

Uses REDAXO CMS structure with multi-category fetching.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from bs4 import BeautifulSoup


if TYPE_CHECKING:
    from bs4 import Tag

from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sources.base import (
    BaseSource,
    create_http_client,
    register_source,
)


__all__ = ["FaustSource"]

logger = logging.getLogger(__name__)

# Categories to fetch with their event types
# Format: (rub parameter, event_type, requires_english_filter)
FAUST_CATEGORIES: list[tuple[int, str, bool]] = [
    (2, "concert", False),  # Livemusik - all events
    (1, "party", False),  # Party - all events (music, no language)
    (4, "theater", True),  # Bühne - English only
]

# Keywords that indicate English language content
ENGLISH_KEYWORDS = [
    "english",
    "englisch",
    " en ",
    "(en)",
    "[en]",
    "in english",
    "auf englisch",
]


@register_source("faust_hannover")
class FaustSource(BaseSource):
    """Scraper for Kulturzentrum Faust Hannover.

    Fetches upcoming events from the venue website across multiple categories:
    - Livemusik (rub=2): All concerts and live music
    - Party (rub=1): All club nights and DJ events
    - Bühne (rub=4): Theater/comedy events in English only

    Website: https://www.kulturzentrum-faust.de/veranstaltungen.html

    Attributes:
        source_name: "Faust"
        source_type: "concert"
    """

    source_name: ClassVar[str] = "Faust"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 40  # Increased for multiple categories

    BASE_URL: ClassVar[str] = "https://www.kulturzentrum-faust.de"
    ADDRESS: ClassVar[str] = "Zur Bettfedernfabrik 3, 30451 Hannover"

    # Categories available: 1=Party, 2=Livemusik, 3=Ausstellung, 4=Bühne,
    # 5=Markt, 6=Gesellschaft, 7=Literatur, 8=Fest

    def fetch(self) -> list[Event]:
        """Fetch events from Kulturzentrum Faust across multiple categories.

        Fetches from:
        - Livemusik (rub=2): All events
        - Party (rub=1): All events
        - Bühne (rub=4): English language events only

        Returns:
            List of Event objects with category="radar".

        Raises:
            httpx.RequestError: If the HTTP request fails.
        """
        logger.info("Fetching concerts from %s", self.source_name)

        all_events: list[Event] = []
        seen_urls: set[str] = set()

        with create_http_client() as client:
            for rub, event_type, requires_english in FAUST_CATEGORIES:
                url = f"{self.BASE_URL}/veranstaltungen.html?rub={rub}"
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, "html.parser")

                    events = self._parse_events(
                        soup,
                        event_type=event_type,
                        requires_english=requires_english,
                        seen_urls=seen_urls,
                    )
                    all_events.extend(events)
                    logger.debug(
                        "Category rub=%d (%s): found %d events",
                        rub,
                        event_type,
                        len(events),
                    )

                    # Small delay between category requests
                    time.sleep(0.3)

                except Exception as exc:
                    logger.warning(
                        "Failed to fetch Faust category rub=%d: %s", rub, exc
                    )

        # Sort by date and apply limit
        all_events.sort(key=lambda e: e.date)
        if self.max_events:
            all_events = all_events[: self.max_events]

        logger.info("Found %d events from %s", len(all_events), self.source_name)
        return all_events

    def _parse_events(
        self,
        soup: BeautifulSoup,
        event_type: str = "concert",
        requires_english: bool = False,
        seen_urls: set[str] | None = None,
    ) -> list[Event]:
        """Parse all events from the page.

        The page structure uses <a> tags linking to event detail pages.
        Each event block contains date, title, location, and pricing info.

        Args:
            soup: Parsed HTML document.
            event_type: Type of event (concert, party, theater).
            requires_english: If True, only include English language events.
            seen_urls: Set of already-seen URLs for deduplication across categories.

        Returns:
            List of parsed Event objects.
        """
        events: list[Event] = []
        if seen_urls is None:
            seen_urls = set()

        # Find all event links - they point to /veranstaltungen/month/date-slug.html
        event_links = soup.find_all(
            "a", href=re.compile(r"/veranstaltungen/\w+/\d{6}-[\w-]+\.html")
        )

        # Deduplicate by href (same event may appear multiple times)
        unique_links: list[Tag] = []
        for link in event_links:
            href = link.get("href", "")
            if href and href not in seen_urls:
                seen_urls.add(href)
                unique_links.append(link)

        for link in unique_links:
            event = self._parse_event(
                link,
                event_type=event_type,
                requires_english=requires_english,
            )
            if event:
                events.append(event)

        return events

    def _parse_event(
        self,
        link: Tag,
        event_type: str = "concert",
        requires_english: bool = False,
    ) -> Event | None:
        """Parse a single event from its link element.

        Args:
            link: BeautifulSoup Tag element (anchor tag with event link).
            event_type: Type of event (concert, party, theater).
            requires_english: If True, skip events without English indicators.

        Returns:
            Parsed Event or None if parsing fails or filters apply.
        """
        try:
            href = link.get("href", "")
            if not href:
                return None

            # Build full URL
            event_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

            # Extract date from URL: /veranstaltungen/november/211125-le-fly.html
            event_date = self._parse_date_from_url(href)
            if not event_date:
                return None

            # Get the text content and parse it
            text_content = link.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in text_content.split("\n") if line.strip()]

            if not lines:
                return None

            # Parse the structured content
            title, time_str, location, price = self._parse_event_content(lines)

            if not title:
                return None

            # For Bühne events, check if it's in English
            if requires_english:
                full_text = " ".join(lines).lower()
                if not self._is_english_event(title, full_text):
                    logger.debug("Skipping non-English Bühne event: %s", title)
                    return None

            # Extract image URL if available
            image_url = self._extract_image_url(link)

            return Event(
                title=title,
                date=event_date,
                venue=self.source_name,
                url=event_url,
                category="radar",
                metadata={
                    "time": time_str,
                    "location": location,  # Sub-venue within Faust
                    "price": price,
                    "event_type": event_type,
                    "image_url": image_url,
                    "address": self.ADDRESS,
                },
            )

        except Exception as exc:
            logger.debug("Error parsing %s event: %s", self.source_name, exc)
            return None

    def _is_english_event(self, title: str, description: str) -> bool:
        """Check if an event appears to be in English.

        Args:
            title: Event title.
            description: Full text description of the event.

        Returns:
            True if the event appears to be in English.
        """
        combined_text = f"{title} {description}".lower()

        for keyword in ENGLISH_KEYWORDS:
            if keyword in combined_text:
                return True

        return False

    def _parse_date_from_url(self, href: str) -> datetime | None:
        """Extract date from URL pattern.

        URL format: /veranstaltungen/november/211125-le-fly.html
        Date part: 211125 = 21.11.25 (day.month.year)

        Args:
            href: Event URL path.

        Returns:
            Parsed datetime or None.
        """
        # Extract date from URL: DDMMYY format
        match = re.search(r"/(\d{2})(\d{2})(\d{2})-", href)
        if not match:
            return None

        try:
            day, month, year = match.groups()
            # Convert 2-digit year to 4-digit (25 -> 2025)
            full_year = 2000 + int(year)
            return datetime(full_year, int(month), int(day), 20, 0, tzinfo=BERLIN_TZ)
        except (ValueError, TypeError):
            return None

    def _parse_event_content(self, lines: list[str]) -> tuple[str, str, str, str]:
        """Parse event details from text content.

        Typical structure:
        - Line with date: "Fr, 21.11.25"
        - Title line
        - Description/subtitle
        - Location: "60er-Jahre Halle" or similar
        - Price: "VVK 25€ / AK 32€"
        - Time: "Einlass: 18:30 Uhr / Beginn: 19:30 Uhr"

        Args:
            lines: List of text lines from event element.

        Returns:
            Tuple of (title, time, location, price).
        """
        title = ""
        time_str = "20:00"
        location = ""
        price = ""

        for line in lines:
            # Skip date lines (e.g., "Fr, 21.11.25")
            if re.match(r"^[A-Za-z]{2},\s*\d{1,2}\.\d{1,2}\.\d{2}", line):
                continue

            # Extract time from "Einlass: HH:MM" or "Beginn: HH:MM"
            time_match = re.search(r"Beginn[:\s]*(\d{1,2})[:\.](\d{2})", line)
            if time_match:
                time_str = f"{time_match.group(1)}:{time_match.group(2)}"
                continue

            # Also check for simple time format
            if "Einlass" in line or "Beginn" in line:
                simple_time = re.search(r"(\d{1,2})[:\.](\d{2})\s*Uhr", line)
                if simple_time:
                    time_str = f"{simple_time.group(1)}:{simple_time.group(2)}"
                continue

            # Extract price (VVK/AK pattern)
            if "VVK" in line or "AK" in line or "€" in line:
                price = line
                continue

            # Known locations within Faust
            known_locations = [
                "60er-Jahre Halle",
                "Mephisto",
                "Warenannahme",
                "Kunsthalle",
                "Café",
                "Gretchen",
            ]
            if any(loc in line for loc in known_locations):
                location = line
                continue

            # First substantial line is likely the title
            if not title and len(line) > 3 and not line.startswith("Einlass"):
                title = line

        return title, time_str, location, price

    def _extract_image_url(self, link: Tag) -> str:
        """Extract image URL from event link.

        Args:
            link: BeautifulSoup Tag element.

        Returns:
            Image URL or empty string.
        """
        img_elem = link.find("img")
        if not img_elem:
            return ""

        src = img_elem.get("src") or img_elem.get("data-src")
        if not src:
            return ""

        image_url = str(src)
        if not image_url.startswith("http"):
            image_url = f"{self.BASE_URL}{image_url}"
        return image_url
