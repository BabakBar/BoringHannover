"""Broncos Hannover source.

Fetches upcoming events for the Broncos venue via Stadtkind Kalender.
Stadtkind provides structured HTML with ISO datetimes per event, which
is stable and avoids scraping social media.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from boringhannover.constants import BERLIN_TZ
from boringhannover.genre import normalize_genre
from boringhannover.models import Event
from boringhannover.sources.base import BaseSource, create_http_client, register_source


__all__ = ["BroncosSource"]

logger = logging.getLogger(__name__)


@register_source("broncos")
class BroncosSource(BaseSource):
    """Scraper for Broncos Hannover (via Stadtkind Kalender).

    Website: https://www.stadtkind-kalender.de/ort/broncos

    Attributes:
        source_name: "Broncos"
        source_type: "concert"
    """

    source_name: ClassVar[str] = "Broncos"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 40

    URL: ClassVar[str] = "https://www.stadtkind-kalender.de/ort/broncos"
    BASE_URL: ClassVar[str] = "https://www.stadtkind-kalender.de"
    ADDRESS: ClassVar[str] = "Schwarzer Bär 7, 30449 Hannover"

    SELECTOR_EVENT: ClassVar[str] = "article.event"
    SELECTOR_LINK: ClassVar[str] = "a.event__link"
    SELECTOR_TIME: ClassVar[str] = "time.event__start-time"
    SELECTOR_TITLE: ClassVar[str] = "h3.event__title"
    SELECTOR_TAGLINE: ClassVar[str] = "span.event__tagline"

    def fetch(self) -> list[Event]:
        """Fetch event listings from Stadtkind Kalender.

        Returns:
            List of Event objects with category="radar".
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
        """Parse all events from the Stadtkind venue page."""
        events: list[Event] = []
        for item in soup.select(self.SELECTOR_EVENT):
            event = self._parse_event(item)
            if event:
                events.append(event)
                if self.max_events and len(events) >= self.max_events:
                    break
        return events

    def _parse_event(self, item: Tag) -> Event | None:
        """Parse a single event card."""
        try:
            link = item.select_one(self.SELECTOR_LINK)
            if not link:
                return None
            href = str(link.get("href", "")).strip()
            if not href:
                return None
            if href.startswith("/"):
                href = f"{self.BASE_URL}{href}"

            time_elem = item.select_one(self.SELECTOR_TIME)
            if not time_elem:
                return None
            datetime_str = str(time_elem.get("datetime", "")).strip()
            event_date = self._parse_datetime(datetime_str)
            if not event_date:
                return None

            title_elem = item.select_one(self.SELECTOR_TITLE)
            title = title_elem.get_text(strip=True) if title_elem else ""
            if not title:
                return None

            raw_genre = ""
            tagline_elem = item.select_one(self.SELECTOR_TAGLINE)
            if tagline_elem:
                raw_genre = tagline_elem.get_text(strip=True)

            genre = normalize_genre(raw_genre) if raw_genre else None

            return Event(
                title=title,
                date=event_date,
                venue=self.source_name,
                url=href,
                category="radar",
                metadata={
                    "time": event_date.strftime("%H:%M"),
                    "genre": genre or raw_genre or "",
                    "genre_source": "stadtkind_tagline" if raw_genre else "",
                    "event_type": "concert",
                    "address": self.ADDRESS,
                },
            )
        except Exception as exc:
            logger.debug("Error parsing %s event: %s", self.source_name, exc)
            return None

    def _parse_datetime(self, datetime_str: str) -> datetime | None:
        """Parse ISO datetime with timezone.

        Stadtkind uses ISO 8601 strings like '2026-01-23T20:00:00+01:00'.
        """
        if not datetime_str:
            return None
        try:
            dt = datetime.fromisoformat(datetime_str)
        except ValueError:
            return None
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            return dt.replace(tzinfo=BERLIN_TZ)
        return dt.astimezone(BERLIN_TZ)
