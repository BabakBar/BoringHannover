"""ZAG Arena Hannover source.

Fetches upcoming concerts and events from ZAG Arena website.
Uses WordPress Event Manager (WPEM) selectors for HTML parsing.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from bs4 import BeautifulSoup

from kinoweek.config import GERMAN_MONTH_MAP

if TYPE_CHECKING:
    from bs4 import Tag
from kinoweek.models import Event
from kinoweek.sources.base import (
    BaseSource,
    create_http_client,
    parse_german_date,
    register_source,
)

__all__ = ["ZAGArenaSource"]

logger = logging.getLogger(__name__)


@register_source("zag_arena")
class ZAGArenaSource(BaseSource):
    """Scraper for ZAG Arena Hannover.

    Fetches upcoming concerts and events from the venue website.
    Uses WordPress Event Manager (WPEM) plugin selectors.

    Website: https://www.zag-arena-hannover.de/veranstaltungen/

    Attributes:
        source_name: "ZAG Arena"
        source_type: "concert"
    """

    source_name: ClassVar[str] = "ZAG Arena"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 15

    # Configuration
    URL: ClassVar[str] = "https://www.zag-arena-hannover.de/veranstaltungen/"
    BASE_URL: ClassVar[str] = "https://www.zag-arena-hannover.de"
    ADDRESS: ClassVar[str] = "Expo Plaza 7, 30539 Hannover"

    # CSS Selectors (WordPress Event Manager)
    SELECTOR_EVENT: ClassVar[str] = ".wpem-event-layout-wrapper"
    SELECTOR_TITLE: ClassVar[str] = ".wpem-heading-text"
    SELECTOR_DATE_TIME: ClassVar[str] = ".wpem-event-date-time-text"
    SELECTOR_DATE: ClassVar[str] = ".wpem-date"
    SELECTOR_MONTH: ClassVar[str] = ".wpem-month"
    SELECTOR_LINK: ClassVar[str] = "a.wpem-event-action-url"

    def fetch(self) -> list[Event]:
        """Fetch concert events from ZAG Arena.

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
        """Parse all events from the page.

        Args:
            soup: Parsed HTML document.

        Returns:
            List of parsed Event objects.
        """
        events: list[Event] = []
        event_items = soup.select(self.SELECTOR_EVENT)

        limit = self.max_events or len(event_items)
        for item in event_items[:limit]:
            event = self._parse_event(item)
            if event:
                events.append(event)

        return events

    def _parse_event(self, item: Tag) -> Event | None:
        """Parse a single event item.

        Args:
            item: BeautifulSoup Tag element representing one event.

        Returns:
            Parsed Event or None if parsing fails.
        """
        try:
            # Extract title
            title_elem = item.select_one(self.SELECTOR_TITLE)
            if not title_elem:
                return None
            title = title_elem.get_text(strip=True)

            # Parse date from date-time element
            event_date, time_str = self._parse_date(item)
            if not event_date:
                return None

            # Extract URL
            link_elem = item.select_one(self.SELECTOR_LINK)
            if not link_elem:
                return None
            href = link_elem.get("href")
            event_url = str(href) if href else ""
            if event_url and not event_url.startswith("http"):
                event_url = f"{self.BASE_URL}{event_url}"

            # Extract image URL if available
            image_url = self._extract_image_url(item)

            # Determine event type from URL
            event_type = self._determine_event_type(event_url)

            return Event(
                title=title,
                date=event_date,
                venue=self.source_name,
                url=event_url,
                category="radar",
                metadata={
                    "time": time_str,
                    "event_type": event_type,
                    "image_url": image_url,
                    "address": self.ADDRESS,
                },
            )

        except Exception as exc:
            logger.debug("Error parsing %s event: %s", self.source_name, exc)
            return None

    def _parse_date(self, item: Tag) -> tuple[datetime | None, str]:
        """Parse date and time from event item.

        Args:
            item: BeautifulSoup Tag element.

        Returns:
            Tuple of (datetime, time_string).
        """
        event_date = None
        time_str = "20:00"

        # Try date-time text element first
        date_time_elem = item.select_one(self.SELECTOR_DATE_TIME)
        if date_time_elem:
            date_text = date_time_elem.get_text(strip=True)
            event_date = parse_german_date(date_text)
            # Extract time if available
            time_match = re.search(r"(\d{1,2}):(\d{2})", date_text)
            if time_match:
                time_str = f"{time_match.group(1)}:{time_match.group(2)}"

        if not event_date:
            # Fallback to day/month elements
            day_elem = item.select_one(self.SELECTOR_DATE)
            month_elem = item.select_one(self.SELECTOR_MONTH)
            if day_elem and month_elem:
                try:
                    day = int(day_elem.get_text(strip=True))
                    month_str = month_elem.get_text(strip=True).rstrip(".")
                    month = GERMAN_MONTH_MAP.get(month_str.lower(), 1)
                    # Use next year if month is before current month
                    year = datetime.now().year
                    if month < datetime.now().month:
                        year += 1
                    event_date = datetime(year, month, day, 20, 0)
                except (ValueError, TypeError):
                    pass

        return event_date, time_str

    def _extract_image_url(self, item: Tag) -> str:
        """Extract image URL from event item.

        Args:
            item: BeautifulSoup Tag element.

        Returns:
            Image URL or empty string.
        """
        img_elem = item.select_one("img")
        if not img_elem:
            return ""

        src = img_elem.get("src") or img_elem.get("data-src")
        image_url = str(src) if src else ""
        if image_url and not image_url.startswith("http"):
            image_url = f"{self.BASE_URL}{image_url}"
        return image_url

    @staticmethod
    def _determine_event_type(url: str) -> str:
        """Determine event type from URL patterns.

        Args:
            url: Event URL.

        Returns:
            Event type string.
        """
        url_lower = url.lower()
        if "sport" in url_lower:
            return "sport"
        if "show" in url_lower or "comedy" in url_lower:
            return "show"
        return "concert"
