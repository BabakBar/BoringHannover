"""Cafe Glocksee Hannover source.

Fetches upcoming concerts and events from Cafe Glocksee - a music venue
and cultural center in Hannover. Uses the Prismic CMS API to fetch event data.

Website: https://cafe-glocksee.de
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sources.base import BaseSource, create_http_client, register_source

if TYPE_CHECKING:
    import httpx


__all__ = ["GlockseeSource"]

logger = logging.getLogger(__name__)


@register_source("glocksee")
class GlockseeSource(BaseSource):
    """Scraper for Cafe Glocksee Hannover.

    Fetches upcoming concerts and events from the venue via Prismic CMS API.
    Includes concerts (Konzert) and party events.

    Website: https://cafe-glocksee.de

    Attributes:
        source_name: "Glocksee"
        source_type: "concert"
    """

    source_name: ClassVar[str] = "Glocksee"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 30

    # Prismic CMS API configuration
    PRISMIC_API_URL: ClassVar[str] = "https://cafe-glocksee.cdn.prismic.io/api/v2"
    BASE_URL: ClassVar[str] = "https://cafe-glocksee.de"
    ADDRESS: ClassVar[str] = "Glockseestraße 35, 30169 Hannover"

    def fetch(self) -> list[Event]:
        """Fetch concert events from Cafe Glocksee.

        Returns:
            List of Event objects with category="radar".

        Raises:
            httpx.RequestError: If the HTTP request fails.
        """
        logger.info("Fetching concerts from %s", self.source_name)

        with create_http_client() as client:
            # First, get the API reference
            ref = self._get_api_ref(client)
            if not ref:
                logger.error("Failed to get Prismic API reference")
                return []

            # Fetch events from Prismic
            events = self._fetch_events(client, ref)

        logger.info("Found %d events from %s", len(events), self.source_name)
        return events

    def _get_api_ref(self, client: httpx.Client) -> str | None:
        """Get the current API reference from Prismic.

        Args:
            client: HTTP client instance.

        Returns:
            API reference string or None if request fails.
        """
        try:
            response = client.get(self.PRISMIC_API_URL)
            response.raise_for_status()
            data = response.json()
            refs = data.get("refs", [])
            for ref_obj in refs:
                if ref_obj.get("isMasterRef"):
                    return ref_obj.get("ref")
            # If no master ref found
            return None
        except Exception:
            logger.exception("Failed to get Prismic API ref")
            return None

    def _fetch_events(self, client: httpx.Client, ref: str) -> list[Event]:
        """Fetch all events from Prismic API.

        Args:
            client: HTTP client instance.
            ref: Prismic API reference.

        Returns:
            List of parsed Event objects.
        """
        events: list[Event] = []
        page = 1
        page_size = 20
        now = datetime.now(BERLIN_TZ)

        search_url = f"{self.PRISMIC_API_URL}/documents/search"

        while True:
            try:
                # Query for event documents, ordered by date
                params = {
                    "ref": ref,
                    "q": '[[at(document.type, "event")]]',
                    "orderings": "[my.event.datetime]",
                    "page": page,
                    "pageSize": page_size,
                }

                response = client.get(search_url, params=params)
                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])
                if not results:
                    break

                # Parse each event
                for result in results:
                    event = self._parse_event(result, now)
                    if event:
                        events.append(event)

                # Check if we should continue pagination
                if self.max_events and len(events) >= self.max_events:
                    break

                # Check if there's a next page
                if not data.get("next_page"):
                    break

                page += 1

            except Exception as exc:
                logger.warning(
                    "Failed to fetch page %d from %s: %s", page, self.source_name, exc
                )
                break

        # Sort by date and apply limit
        events.sort(key=lambda e: e.date)
        if self.max_events:
            events = events[: self.max_events]

        return events

    def _parse_event(self, result: dict[str, Any], now: datetime) -> Event | None:
        """Parse a single event from Prismic API response.

        Args:
            result: Event data from Prismic API.
            now: Current datetime for filtering past events.

        Returns:
            Parsed Event or None if parsing fails or event is in the past.
        """
        try:
            data = result.get("data", {})

            # Extract title
            title_parts = data.get("title", [])
            if not title_parts or not isinstance(title_parts, list):
                return None
            title = title_parts[0].get("text", "").strip()
            if not title:
                return None

            # Extract and parse datetime
            datetime_str = data.get("datetime")
            if not datetime_str:
                return None

            event_date = datetime.fromisoformat(datetime_str)
            event_date = event_date.astimezone(BERLIN_TZ)

            # Skip past events
            if event_date < now:
                return None

            # Build event URL
            uid = result.get("uid", "")
            event_url = f"{self.BASE_URL}#/event/{uid}" if uid else self.BASE_URL

            # Extract event type
            event_type = data.get("event_type", "Konzert")

            # Extract description
            description = ""
            text_parts = data.get("text", [])
            if text_parts and isinstance(text_parts, list):
                description_parts = []
                for part in text_parts[:2]:  # First 2 paragraphs
                    if isinstance(part, dict) and part.get("type") == "paragraph":
                        text = part.get("text", "").strip()
                        if text:
                            description_parts.append(text)
                description = " ".join(description_parts)

            # Extract image URL
            image_url = ""
            teaser_image = data.get("teaser_image", {})
            if isinstance(teaser_image, dict):
                image_url = teaser_image.get("url", "")

            # Extract support bands
            support_bands = []
            bands = data.get("bands", [])
            if isinstance(bands, list):
                for band in bands:
                    if isinstance(band, dict):
                        band_name = band.get("name", "").strip()
                        band_role = band.get("role", "").strip()
                        if band_name and band_role:
                            support_bands.append(f"{band_name} ({band_role})")

            return Event(
                title=title,
                date=event_date,
                venue=self.source_name,
                url=event_url,
                category="radar",
                metadata={
                    "time": event_date.strftime("%H:%M"),
                    "event_type": event_type,
                    "description": description[:300] if description else "",
                    "image_url": image_url,
                    "support": ", ".join(support_bands) if support_bands else "",
                    "address": self.ADDRESS,
                },
            )

        except Exception as exc:
            logger.debug("Error parsing %s event: %s", self.source_name, exc)
            return None
