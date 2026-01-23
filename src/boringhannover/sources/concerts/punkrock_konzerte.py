"""Punkrock-Konzerte Hannover source.

Fetches upcoming punk/hardcore gigs from punkrock-konzerte.de for
Hannover and surrounding areas.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time
from typing import TYPE_CHECKING, ClassVar

from bs4 import BeautifulSoup

from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sources.base import BaseSource, create_http_client, register_source


if TYPE_CHECKING:
    from bs4 import Tag

__all__ = ["PunkrockKonzerteSource"]

logger = logging.getLogger(__name__)


@register_source("punkrock_konzerte")
class PunkrockKonzerteSource(BaseSource):
    """Scraper for punkrock-konzerte.de Hannover listings.

    Website: https://www.punkrock-konzerte.de/gigs-termine-hannover/

    Attributes:
        source_name: "Punkrock-Konzerte"
        source_type: "concert"
    """

    source_name: ClassVar[str] = "Punkrock-Konzerte"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = None

    URL: ClassVar[str] = "https://www.ce.punkrock-konzerte.de/gigs-termine-hannover/"
    DEFAULT_TIME: ClassVar[time] = time(20, 0)

    def fetch(self) -> list[Event]:
        """Fetch punk/hardcore concerts from punkrock-konzerte.de.

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
        """Parse all events from the Hannover listings page.

        Args:
            soup: Parsed HTML document.

        Returns:
            List of parsed Event objects.
        """
        events: list[Event] = []

        for row in soup.select(
            "div.row[itemscope][itemtype='http://schema.org/Event']"
        ):
            event = self._parse_event(row)
            if event:
                events.append(event)
                if self.max_events and len(events) >= self.max_events:
                    break

        return events

    def _parse_event(self, row: Tag) -> Event | None:
        """Parse a single event row.

        Args:
            row: BeautifulSoup Tag element for one event.

        Returns:
            Parsed Event or None if parsing fails.
        """
        try:
            title = self._extract_title(row)
            if not title:
                return None

            event_date = self._extract_date(row)
            if not event_date:
                return None

            if event_date < datetime.now(BERLIN_TZ):
                return None

            venue = self._extract_venue(row) or self.source_name
            city = self._extract_city(row)
            url = self._extract_url(row) or self.URL

            return Event(
                title=title,
                date=event_date,
                venue=venue,
                url=url,
                category="radar",
                metadata={
                    "time": event_date.strftime("%H:%M"),
                    "event_type": "concert",
                    "genre": "Punk / Hardcore",
                    "genre_source": "source_implicit",
                    "address": city,
                },
            )

        except Exception as exc:
            logger.debug("Error parsing %s event: %s", self.source_name, exc)
            return None

    def _extract_title(self, row: Tag) -> str:
        title_elem = row.find("span", class_="b")
        if not title_elem:
            return ""
        return title_elem.get_text(strip=True)

    def _extract_venue(self, row: Tag) -> str:
        venue_elem = row.select_one("[itemprop='location'] [itemprop='name']")
        if not venue_elem:
            return ""
        return venue_elem.get_text(strip=True)

    def _extract_city(self, row: Tag) -> str:
        city_elem = row.select_one("[itemprop='location'] [itemprop='address']")
        if not city_elem:
            return ""
        return city_elem.get_text(strip=True)

    def _extract_url(self, row: Tag) -> str:
        link = row.select_one("a.info")
        if link and link.get("href"):
            return str(link["href"])

        meta_url = row.select_one("meta[itemprop='url']")
        if meta_url and meta_url.get("content"):
            return str(meta_url["content"])

        return ""

    def _extract_date(self, row: Tag) -> datetime | None:
        start_meta = row.select_one("meta[itemprop='startDate']")
        if start_meta and start_meta.get("content"):
            parsed = self._parse_iso_date(str(start_meta["content"]))
            if parsed:
                return parsed

        date_box = row.find("div", class_="dateBox")
        if date_box:
            text = date_box.get_text(" ", strip=True)
            match = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", text)
            if match:
                return self._parse_german_numeric_date(match.group(1))

        return None

    def _parse_iso_date(self, value: str) -> datetime | None:
        try:
            if "T" in value:
                parsed = datetime.fromisoformat(value)
                if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
                    parsed = parsed.replace(tzinfo=BERLIN_TZ)
                else:
                    parsed = parsed.astimezone(BERLIN_TZ)
                if parsed.hour == 0 and parsed.minute == 0:
                    parsed = parsed.replace(
                        hour=self.DEFAULT_TIME.hour,
                        minute=self.DEFAULT_TIME.minute,
                    )
                return parsed

            parsed_date = date.fromisoformat(value)
            return datetime.combine(parsed_date, self.DEFAULT_TIME, tzinfo=BERLIN_TZ)

        except ValueError as exc:
            logger.debug("Failed to parse date '%s': %s", value, exc)
            return None

    def _parse_german_numeric_date(self, value: str) -> datetime | None:
        try:
            day_str, month_str, year_str = value.split(".")
            parsed_date = date(int(year_str), int(month_str), int(day_str))
            return datetime.combine(
                parsed_date,
                self.DEFAULT_TIME,
                tzinfo=BERLIN_TZ,
            )
        except ValueError as exc:
            logger.debug("Failed to parse date '%s': %s", value, exc)
            return None
