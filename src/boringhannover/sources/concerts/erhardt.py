"""Erhardt Café Hannover source.

Fetches upcoming events from Erhardt Café - a cozy café in Hannover's
Lister Meile with chess nights, game nights, karaoke, live music, and more.

The website uses Wix Events. This scraper fetches events via the Wix Events API:
1. Fetch dynamic instance token from /_api/v2/dynamicmodel
2. Query /_api/wix-events-web/v1/events with the instance token

This approach is more reliable than HTML scraping (which only returns partial data)
and eliminates the need for static event lists.

Website: https://www.erhardt.cafe/events
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, ClassVar

from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sources.base import BaseSource, create_http_client, register_source


__all__ = ["ErhardtCafeSource"]

logger = logging.getLogger(__name__)

# Wix Events app ID (used to extract instance token)
WIX_EVENTS_APP_ID = "140603ad-af8d-84a5-2c80-a0f60cb47351"


@register_source("erhardt_cafe")
class ErhardtCafeSource(BaseSource):
    """Scraper for Erhardt Café Hannover events.

    Fetches events via the Wix Events API. The API requires:
    1. Fetching a dynamic instance token from /_api/v2/dynamicmodel
    2. Querying events with that token

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
    max_events: ClassVar[int | None] = 50

    # Configuration
    URL: ClassVar[str] = "https://www.erhardt.cafe/events"
    BASE_URL: ClassVar[str] = "https://www.erhardt.cafe"
    ADDRESS: ClassVar[str] = "Limmerstraße 46, 30451 Hannover"

    # Wix API endpoints
    DYNAMICMODEL_URL: ClassVar[str] = "https://www.erhardt.cafe/_api/v2/dynamicmodel"
    EVENTS_API_URL: ClassVar[str] = (
        "https://www.erhardt.cafe/_api/wix-events-web/v1/events"
    )

    def fetch(self) -> list[Event]:
        """Fetch events from Erhardt Café via Wix Events API.

        1. Fetches dynamic instance token from /_api/v2/dynamicmodel
        2. Queries events API with that token

        Returns:
            List of Event objects with category="radar".

        Raises:
            httpx.RequestError: If the HTTP request fails.
        """
        logger.info("Fetching events from %s", self.source_name)

        with create_http_client() as client:
            # Step 1: Get instance token
            instance = self._get_instance_token(client)
            if not instance:
                logger.warning("Failed to get Wix instance token")
                return []

            # Step 2: Fetch events from API
            events = self._fetch_events_from_api(client, instance)

        # Sort by date
        events.sort(key=lambda e: e.date)

        # Apply max_events limit
        if self.max_events:
            events = events[: self.max_events]

        logger.info("Found %d events from %s", len(events), self.source_name)
        return events

    def _get_instance_token(self, client: Any) -> str | None:
        """Fetch Wix instance token from dynamicmodel endpoint.

        Args:
            client: HTTP client instance.

        Returns:
            Instance token string or None if not found.
        """
        try:
            response = client.get(self.DYNAMICMODEL_URL)
            response.raise_for_status()
            data = response.json()

            # Instance token is in apps[WIX_EVENTS_APP_ID].instance
            apps = data.get("apps", {})
            app_data = apps.get(WIX_EVENTS_APP_ID, {})
            instance = app_data.get("instance")

            if instance:
                logger.debug("Got Wix instance token")
                return str(instance)

            logger.warning("Instance token not found in dynamicmodel response")
            return None

        except Exception as exc:
            logger.warning("Failed to fetch dynamicmodel: %s", exc)
            return None

    def _fetch_events_from_api(self, client: Any, instance: str) -> list[Event]:
        """Fetch events from Wix Events API.

        Args:
            client: HTTP client instance.
            instance: Wix instance token.

        Returns:
            List of parsed Event objects.
        """
        events: list[Event] = []

        try:
            # Fetch with limit=50 to get all events
            params = {"instance": instance, "limit": "50", "offset": "0"}
            response = client.get(self.EVENTS_API_URL, params=params)
            response.raise_for_status()
            data = response.json()

            event_list = data.get("events", [])
            total = data.get("total", len(event_list))
            logger.debug("API returned %d events (total: %d)", len(event_list), total)

            for event_data in event_list:
                event = self._parse_wix_event(event_data)
                if event:
                    events.append(event)

        except Exception as exc:
            logger.warning("Failed to fetch events from API: %s", exc)

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

            # Get formatted time from scheduling (None if not available)
            time_str = scheduling.get("startTimeFormatted") or ""

            # Get location
            location = event_data.get("location", {})
            address = location.get("address", self.ADDRESS)

            # Build event URL from slug
            slug = event_data.get("slug", "")
            event_url = f"{self.BASE_URL}/event-details/{slug}" if slug else self.URL

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
        """Parse ISO format date string to datetime in Berlin timezone.

        Handles formats like:
        - "2025-10-15T17:00:00.000Z"
        - "2025-10-15T17:00:00Z"

        Args:
            date_str: ISO format date string (UTC with Z suffix).

        Returns:
            Parsed datetime in Europe/Berlin timezone, or None.
        """
        try:
            # Remove milliseconds if present: "2025-10-15T17:00:00.000Z" -> "2025-10-15T17:00:00Z"
            if ".000Z" in date_str:
                date_str = date_str.replace(".000Z", "Z")

            # Replace Z with +00:00 for proper UTC parsing
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"

            # Parse as timezone-aware UTC datetime
            utc_date = datetime.fromisoformat(date_str)

            # Convert to Berlin time (handles DST automatically)
            return utc_date.astimezone(BERLIN_TZ)

        except ValueError as exc:
            logger.debug("Failed to parse date '%s': %s", date_str, exc)
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
