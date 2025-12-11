"""Erhardt Café Hannover source.

Fetches upcoming events from Erhardt Café - a cozy café in Hannover's
Lister Meile with chess nights, game nights, karaoke, live music, and more.

The website uses Wix with two event sources:
1. Wix Events widget - Ticketed events (scraped dynamically from embedded JSON)
2. Google Calendar widget - Free events (loaded via iframe, requires static data)

This scraper uses a hybrid approach:
- Dynamically extracts Wix Events from the page HTML
- Supplements with static Google Calendar events (updated periodically)

Website: https://www.erhardt.cafe/events
"""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime
from typing import Any, ClassVar

from bs4 import BeautifulSoup

from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sources.base import (
    BaseSource,
    create_http_client,
    register_source,
)


__all__ = ["ErhardtCafeSource"]

logger = logging.getLogger(__name__)

# Wix Events app ID
WIX_EVENTS_APP_ID = "140603ad-af8d-84a5-2c80-a0f60cb47351"

# Google Calendar events - loaded via iframe, not scrape-able
# Update this list periodically from https://www.erhardt.cafe/events
# Format: (year, month, day, hour, minute, title, event_type)  # noqa: ERA001
# Last updated: 2025-11-23
GOOGLE_CALENDAR_EVENTS: list[tuple[int, int, int, int, int, str, str]] = [
    # November 2025
    (2025, 11, 26, 18, 0, "Schachabend im Erhardt ♟", "games"),
    (2025, 11, 27, 20, 0, "EARN. & VENCINT 🎤 Live im Erhardt", "concert"),
    # December 2025
    (2025, 12, 3, 19, 0, "Kniffelabend 🎲😊", "games"),
    (2025, 12, 10, 17, 30, "Connect & Create 🎄👥", "social"),
    (2025, 12, 11, 20, 0, "Erhardts Karaoke 🎤", "karaoke"),
    (2025, 12, 17, 19, 0, "Tablequiz 🤔❗❓", "quiz"),
    (2025, 12, 27, 20, 0, "Udi Fagundes 🎤 Live im Erhardt", "concert"),
]


@register_source("erhardt_cafe")
class ErhardtCafeSource(BaseSource):
    """Scraper for Erhardt Café Hannover events.

    Fetches events from the Wix-powered website by extracting JSON data
    embedded in script tags. Supports both ticketed events (Wix Events)
    and calendar events.

    Event types include:
    - Chess nights (Schachabend)
    - Game nights (Kniffelabend)
    - Karaoke evenings
    - Live music performances
    - Tablequiz
    - Social events

    Website: https://www.erhardt.cafe/events

    Attributes:
        source_name: "Erhardt Café"
        source_type: "concert"
    """

    source_name: ClassVar[str] = "Erhardt Café"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 20

    # Configuration
    URL: ClassVar[str] = "https://www.erhardt.cafe/events"
    BASE_URL: ClassVar[str] = "https://www.erhardt.cafe"
    ADDRESS: ClassVar[str] = "Limmerstraße 46, 30451 Hannover"

    def fetch(self) -> list[Event]:
        """Fetch events from Erhardt Café website.

        Uses a hybrid approach:
        1. Extracts Wix Events from embedded JSON (ticketed events)
        2. Adds static Google Calendar events (free events)

        Returns:
            List of Event objects with category="radar".

        Raises:
            httpx.RequestError: If the HTTP request fails.
        """
        logger.info("Fetching events from %s", self.source_name)

        events: list[Event] = []

        # First, try to extract Wix Events from the page
        try:
            with create_http_client() as client:
                response = client.get(self.URL)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

            wix_events = self._extract_wix_events(soup, response.text)
            events.extend(wix_events)
            logger.info("Extracted %d Wix Events", len(wix_events))
        except Exception as exc:
            logger.warning("Failed to fetch Wix Events: %s", exc)

        # Add Google Calendar events (static data)
        calendar_events = self._get_google_calendar_events()

        # Merge events, avoiding duplicates by title and date
        existing_keys = {(e.title.lower(), e.date.date()) for e in events}
        for event in calendar_events:
            key = (event.title.lower(), event.date.date())
            if key not in existing_keys:
                events.append(event)
                existing_keys.add(key)

        # Sort by date
        events.sort(key=lambda e: e.date)

        # Apply max_events limit
        if self.max_events:
            events = events[: self.max_events]

        logger.info("Found %d total events from %s", len(events), self.source_name)
        return events

    def _get_google_calendar_events(self) -> list[Event]:
        """Get events from the static Google Calendar data.

        Returns:
            List of Event objects from the static calendar data.
        """
        events: list[Event] = []
        now = datetime.now(BERLIN_TZ)

        for year, month, day, hour, minute, title, event_type in GOOGLE_CALENDAR_EVENTS:
            event_date = datetime(year, month, day, hour, minute, tzinfo=BERLIN_TZ)

            # Skip past events
            if event_date < now:
                continue

            event = Event(
                title=title,
                date=event_date,
                venue=self.source_name,
                url=self.URL,
                category="radar",
                metadata={
                    "time": f"{hour:02d}:{minute:02d}",
                    "event_type": event_type,
                    "address": self.ADDRESS,
                    "source": "google_calendar",
                },
            )
            events.append(event)

        return events

    def _extract_wix_events(self, soup: BeautifulSoup, raw_html: str) -> list[Event]:
        """Extract events from Wix Events widget data.

        Wix embeds event data in <script type="application/json"> tags.
        The structure is in appsWarmupData[WIX_EVENTS_APP_ID].

        Args:
            soup: Parsed HTML document.
            raw_html: Raw HTML string for regex extraction.

        Returns:
            List of parsed Event objects.
        """
        events: list[Event] = []

        # Find all application/json script tags
        script_tags = soup.find_all("script", type="application/json")

        for script in script_tags:
            if not script.string:
                continue

            try:
                # Decode HTML entities and parse JSON
                decoded = html.unescape(script.string)
                data = json.loads(decoded)

                # Look for Wix Events app data in appsWarmupData
                if not isinstance(data, dict):
                    continue

                warmup_data = data.get("appsWarmupData", {})
                if not warmup_data:
                    continue

                # Get events from Wix Events app
                events_app = warmup_data.get(WIX_EVENTS_APP_ID, {})
                if not events_app:
                    continue

                # Events can be in different widget components
                for widget_key, widget_data in events_app.items():
                    if not isinstance(widget_data, dict):
                        continue

                    events_container = widget_data.get("events", {})
                    if not isinstance(events_container, dict):
                        continue

                    event_list = events_container.get("events", [])
                    if not isinstance(event_list, list):
                        continue

                    for event_data in event_list:
                        event = self._parse_wix_event(event_data)
                        if event:
                            events.append(event)
                            if self.max_events and len(events) >= self.max_events:
                                return events

            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.debug("Error parsing JSON script tag: %s", exc)
                continue

        return events

    def _parse_wix_event(self, event_data: dict[str, Any]) -> Event | None:
        """Parse a single Wix event into an Event object.

        Args:
            event_data: Raw event dict from Wix Events API.

        Returns:
            Parsed Event or None if parsing fails.
        """
        try:
            title = event_data.get("title", "")
            if not title:
                return None

            # Parse scheduling data
            scheduling = event_data.get("scheduling", {})
            config = scheduling.get("config", {})

            start_date_str = config.get("startDate", "")
            if not start_date_str:
                return None

            # Parse ISO format date: "2025-10-15T17:00:00.000Z"
            # Convert from UTC to local time (Europe/Berlin)
            event_date = self._parse_iso_date(start_date_str)
            if not event_date:
                return None

            # Skip past events
            if event_date < datetime.now(BERLIN_TZ):
                return None

            # Get formatted time from scheduling
            time_str = scheduling.get("startTimeFormatted", "20:00")

            # Get location
            location = event_data.get("location", {})
            address = location.get("address", self.ADDRESS)

            # Build event URL from slug
            slug = event_data.get("slug", "")
            if slug:
                event_url = f"{self.BASE_URL}/event-details/{slug}"
            else:
                event_url = self.URL

            # Get description
            description = event_data.get("description", "")

            # Determine event type from title
            event_type = self._infer_event_type(title)

            return Event(
                title=title,
                date=event_date,
                venue=self.source_name,
                url=event_url,
                category="radar",
                metadata={
                    "time": time_str,
                    "event_type": event_type,
                    "address": address,
                    "description": description[:200] if description else "",
                },
            )

        except Exception as exc:
            logger.debug("Error parsing Wix event: %s", exc)
            return None

    def _parse_iso_date(self, date_str: str) -> datetime | None:
        """Parse ISO format date string to datetime.

        Handles formats like:
        - "2025-10-15T17:00:00.000Z"
        - "2025-10-15T17:00:00Z"

        Note: Wix stores dates in UTC. We add 1-2 hours for Europe/Berlin.

        Args:
            date_str: ISO format date string.

        Returns:
            Parsed datetime or None.
        """
        # Remove milliseconds and Z suffix for parsing
        clean_str = re.sub(r"\.\d{3}Z$", "", date_str)
        clean_str = re.sub(r"Z$", "", clean_str)

        try:
            # Parse as UTC
            utc_date = datetime.fromisoformat(clean_str)
            # Add 1 hour for CET (simplified - should use proper timezone)
            # In winter (CET) it's UTC+1, in summer (CEST) it's UTC+2
            # For simplicity, we add 1 hour (winter time)
            from datetime import timedelta

            local_date = utc_date + timedelta(hours=1)
            return local_date
        except ValueError:
            return None

    def _infer_event_type(self, title: str) -> str:
        """Infer event type from title.

        Args:
            title: Event title.

        Returns:
            Event type string.
        """
        title_lower = title.lower()

        if "schach" in title_lower:
            return "games"
        if "kniffel" in title_lower:
            return "games"
        if "quiz" in title_lower:
            return "quiz"
        if "karaoke" in title_lower:
            return "karaoke"
        if "live" in title_lower or "konzert" in title_lower:
            return "concert"
        if "connect" in title_lower or "social" in title_lower:
            return "social"

        return "event"
