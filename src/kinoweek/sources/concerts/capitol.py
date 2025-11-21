"""Capitol Hannover source.

Fetches upcoming concerts and events from Capitol Hannover website.
Uses HC-Kartenleger card system selectors for HTML parsing (same as Swiss Life Hall).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from bs4 import Tag

from kinoweek.models import Event
from kinoweek.sources.base import (
    BaseSource,
    create_http_client,
    parse_venue_date,
    register_source,
)

__all__ = ["CapitolSource"]

logger = logging.getLogger(__name__)


@register_source("capitol_hannover")
class CapitolSource(BaseSource):
    """Scraper for Capitol Hannover.

    Fetches upcoming concerts and events from the venue website.
    Uses HC-Kartenleger card system selectors (same as Swiss Life Hall).

    Website: https://www.capitol-hannover.de/events/

    Attributes:
        source_name: "Capitol Hannover"
        source_type: "concert"
    """

    source_name: ClassVar[str] = "Capitol Hannover"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 15

    # Configuration
    URL: ClassVar[str] = "https://www.capitol-hannover.de/events/"
    BASE_URL: ClassVar[str] = "https://www.capitol-hannover.de"
    ADDRESS: ClassVar[str] = "Schwarzer Bär 2, 30449 Hannover"

    # CSS Selectors (HC-Kartenleger system)
    SELECTOR_EVENT: ClassVar[str] = "a.hc-card-link-wrapper"
    SELECTOR_TITLE: ClassVar[str] = "h4, h3"
    SELECTOR_DATE: ClassVar[str] = "time"
    SELECTOR_SUBTITLE: ClassVar[str] = ".hc-card-subtitle, .subtitle, p"

    def fetch(self) -> list[Event]:
        """Fetch concert events from Capitol Hannover.

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
        """Parse a single HC-style event item.

        Args:
            item: BeautifulSoup Tag element representing one event.

        Returns:
            Parsed Event or None if parsing fails.
        """
        try:
            # Extract title from 'title' attribute or h4/h3
            title_attr = item.get("title")
            title = str(title_attr) if title_attr else None
            if not title:
                title_elem = item.select_one(self.SELECTOR_TITLE)
                title = title_elem.get_text(strip=True) if title_elem else None
            if not title:
                return None

            # Parse date from time element (format: "AB22NOV2025")
            date_elem = item.select_one(self.SELECTOR_DATE)
            if not date_elem:
                return None

            date_str = date_elem.get_text(strip=True)
            event_date = parse_venue_date(date_str)
            if not event_date:
                return None

            # Extract URL
            href = item.get("href")
            event_url = str(href) if href else ""
            if event_url and not event_url.startswith("http"):
                event_url = f"{self.BASE_URL}{event_url}"

            # Extract optional metadata
            subtitle = self._extract_subtitle(item, title)
            image_url = self._extract_image_url(item)
            status = self._check_sold_out_status(item)

            return Event(
                title=title,
                date=event_date,
                venue=self.source_name,
                url=event_url,
                category="radar",
                metadata={
                    "time": event_date.strftime("%H:%M"),
                    "subtitle": subtitle,
                    "image_url": image_url,
                    "status": status,
                    "event_type": "concert",
                    "address": self.ADDRESS,
                },
            )

        except Exception as exc:
            logger.debug("Error parsing %s event: %s", self.source_name, exc)
            return None

    def _extract_subtitle(self, item: Tag, title: str) -> str:
        """Extract subtitle/description from event item.

        Args:
            item: BeautifulSoup Tag element.
            title: Event title (to avoid duplication).

        Returns:
            Subtitle string or empty string.
        """
        subtitle_elem = item.select_one(self.SELECTOR_SUBTITLE)
        if not subtitle_elem:
            return ""
        subtitle = subtitle_elem.get_text(strip=True)
        return subtitle if subtitle != title else ""

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

    def _check_sold_out_status(self, item: Tag) -> str:
        """Check if event is sold out.

        Args:
            item: BeautifulSoup Tag element.

        Returns:
            "sold_out" or "available".
        """
        status_elem = item.select_one(".sold-out, .ausverkauft, [class*='sold']")
        if status_elem:
            return "sold_out"

        item_text = item.get_text().lower()
        if "ausverkauft" in item_text or "sold out" in item_text:
            return "sold_out"

        return "available"
