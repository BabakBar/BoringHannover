"""MusikZentrum Hannover source.

Fetches upcoming concerts from MusikZentrum Hannover using JSON-LD
structured data. The venue hosts 100-150 concerts per year across
rock, metal, and alternative genres.
"""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime
from typing import ClassVar

from bs4 import BeautifulSoup

from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sources.base import BaseSource, create_http_client, register_source


__all__ = ["MusikZentrumSource"]

logger = logging.getLogger(__name__)


@register_source("musikzentrum")
class MusikZentrumSource(BaseSource):
    """Scraper for MusikZentrum Hannover.

    Fetches upcoming concerts using JSON-LD structured data embedded
    in the events page. WordPress + The Events Calendar plugin.

    Website: https://musikzentrum-hannover.de/veranstaltungen/

    Attributes:
        source_name: "MusikZentrum"
        source_type: "concert"
    """

    source_name: ClassVar[str] = "MusikZentrum"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 20

    # Configuration
    URL: ClassVar[str] = "https://musikzentrum-hannover.de/veranstaltungen/"
    BASE_URL: ClassVar[str] = "https://musikzentrum-hannover.de"
    ADDRESS: ClassVar[str] = "Emil-Meyer-Str. 26, 30165 Hannover"

    def fetch(self) -> list[Event]:
        """Fetch concert events from MusikZentrum Hannover.

        Uses JSON-LD structured data for clean parsing.

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
        """Parse events from JSON-LD structured data.

        Args:
            soup: Parsed HTML document.

        Returns:
            List of parsed Event objects.
        """
        events: list[Event] = []

        # Find JSON-LD script
        json_ld_script = soup.find("script", type="application/ld+json")
        if not json_ld_script or not json_ld_script.string:
            logger.warning("No JSON-LD data found on %s", self.URL)
            return events

        try:
            data = json.loads(json_ld_script.string)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse JSON-LD: %s", exc)
            return events

        # Data is an array of Event objects
        if not isinstance(data, list):
            data = [data]

        for item in data:
            if item.get("@type") != "Event":
                continue

            event = self._parse_event(item)
            if event:
                events.append(event)
                if self.max_events and len(events) >= self.max_events:
                    break

        return events

    def _parse_event(self, item: dict) -> Event | None:
        """Parse a single event from JSON-LD data.

        Args:
            item: JSON-LD Event object.

        Returns:
            Parsed Event or None if parsing fails.
        """
        try:
            # Extract and decode title (may have HTML entities)
            title = item.get("name", "")
            title = html.unescape(title)
            # Clean up common patterns
            title = re.sub(r"\s*&#\d+;\s*", " ", title)
            title = re.sub(r"\s+", " ", title).strip()

            if not title:
                return None

            # Parse start date (ISO 8601 format)
            start_date_str = item.get("startDate", "")
            event_date = self._parse_iso_date(start_date_str)
            if not event_date:
                return None

            # Extract URL
            event_url = item.get("url", self.URL)

            # Extract image URL
            image_url = item.get("image", "")

            # Extract location details
            location = item.get("location", {})
            address_obj = location.get("address", {})
            address = self._format_address(address_obj)

            # Extract description (clean HTML)
            description = item.get("description", "")
            description = self._clean_description(description)

            return Event(
                title=title,
                date=event_date,
                venue=self.source_name,
                url=event_url,
                category="radar",
                metadata={
                    "time": event_date.strftime("%H:%M"),
                    "image_url": image_url,
                    "description": description[:200] if description else "",
                    "event_type": "concert",
                    "address": address or self.ADDRESS,
                },
            )

        except Exception as exc:
            logger.debug("Error parsing %s event: %s", self.source_name, exc)
            return None

    def _parse_iso_date(self, date_str: str) -> datetime | None:
        """Parse ISO 8601 date string.

        Args:
            date_str: Date string like "2025-11-22T20:00:00+01:00".

        Returns:
            Parsed datetime or None.
        """
        if not date_str:
            return None

        # Try various ISO formats
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                # Remove timezone for simpler parsing
                clean_str = re.sub(r"[+-]\d{2}:\d{2}$", "", date_str)
                return datetime.strptime(clean_str, fmt.replace("%z", "")).replace(
                    tzinfo=BERLIN_TZ
                )
            except ValueError:
                continue

        return None

    def _format_address(self, address_obj: dict) -> str:
        """Format address from JSON-LD PostalAddress object.

        Args:
            address_obj: PostalAddress dict.

        Returns:
            Formatted address string.
        """
        if not address_obj:
            return ""

        parts = [
            address_obj.get("streetAddress", ""),
            address_obj.get("postalCode", ""),
            address_obj.get("addressLocality", ""),
        ]
        return ", ".join(p for p in parts if p)

    def _clean_description(self, description: str) -> str:
        """Clean HTML from description.

        Args:
            description: Raw description with HTML.

        Returns:
            Plain text description.
        """
        if not description:
            return ""

        # Decode HTML entities
        text = html.unescape(description)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Remove common artifacts
        return text.replace("[&hellip;]", "...")
