"""Stumpf Hannover venue event source."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import FALLBACK_TIME
from boringhannover.models import Event
from boringhannover.sources.base import BaseSource, register_source

logger = logging.getLogger(__name__)


@register_source("stumpf_hannover")
class StumpfSource(BaseSource):
    """Scraper for Stumpf Hannover events."""

    name = "Stumpf Hannover"
    url = "https://stumpf-hannover.de/veranstaltungen/"
    type = "concerts"

    async def fetch(self, session: httpx.AsyncClient) -> list[Event]:
        """Fetch and parse events from the Stumpf Hannover event listing."""
        try:
            response = await session.get(self.url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            return self._parse_events(soup)
        except Exception as exc:
            logger.error("Failed to fetch Stumpf Hannover events: %s", exc)
            return []

    def _parse_events(self, soup: BeautifulSoup) -> list[Event]:
        """Extract events from the parsed HTML."""
        events: list[Event] = []
        items = soup.select(".veranstaltung, .event, li.post, .calendar-item")
        for item in items:
            title_el = item.select_one("h3, .title, a[href*='/veranstaltungen/']")
            date_el = item.select_one(".date, time, .datum, .calendar-date")

            if not title_el or not date_el:
                continue

            title = title_el.get_text(strip=True)
            date_str = date_el.get_text(strip=True).replace(" bis", "")

            try:
                date_obj = datetime.strptime(date_str.split(" ")[0], "%d.%m.%Y")
                date_obj = date_obj.replace(hour=20, tzinfo=BERLIN_TZ)
            except ValueError:
                logger.warning("Could not parse date for Stumpf event: %s", date_str)
                continue

            events.append(
                Event(
                    title=title,
                    date=date_obj,
                    venue="Stumpf Hannover",
                    url=self.url,
                    category="radar",
                    metadata={"time_confidence": FALLBACK_TIME},
                )
            )
        return events
