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
from boringhannover.event_time import CONFIRMED_TIME, FALLBACK_TIME
from boringhannover.models import Event
from boringhannover.sources.base import BaseSource, create_http_client, register_source


if TYPE_CHECKING:
    from bs4 import Tag
    from httpx import Client

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
            events = self._parse_events(soup, client)

        logger.info("Found %d events from %s", len(events), self.source_name)
        return events

    def _parse_events(
        self, soup: BeautifulSoup, client: Client | None = None
    ) -> list[Event]:
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
            event = self._parse_event(row, client)
            if event:
                events.append(event)
                if self.max_events and len(events) >= self.max_events:
                    break

        return events

    def _parse_event(self, row: Tag, client: Client | None = None) -> Event | None:
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

            event_date, time_confidence = self._extract_date(row)
            if not event_date:
                return None

            if event_date < datetime.now(BERLIN_TZ):
                return None

            venue = self._extract_venue(row) or self.source_name
            city = self._extract_city(row)
            url = self._extract_url(row) or self.URL
            if time_confidence == FALLBACK_TIME:
                enriched = self._fetch_confirmed_datetime(client, url)
                if enriched:
                    event_date = enriched
                    time_confidence = CONFIRMED_TIME

            return Event(
                title=title,
                date=event_date,
                venue=venue,
                url=url,
                category="radar",
                metadata={
                    "time": event_date.strftime("%H:%M"),
                    "time_confidence": time_confidence,
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
        meta_url = row.select_one("meta[itemprop='url']")
        if meta_url and meta_url.get("content"):
            return str(meta_url["content"])

        link = row.select_one("a.info")
        if link and link.get("href"):
            return str(link["href"])

        return ""

    def _extract_date(self, row: Tag) -> tuple[datetime | None, str]:
        start_meta = row.select_one("meta[itemprop='startDate']")
        if start_meta and start_meta.get("content"):
            parsed = self._parse_iso_date(str(start_meta["content"]))
            if parsed:
                confidence = (
                    CONFIRMED_TIME
                    if "T" in str(start_meta["content"])
                    else FALLBACK_TIME
                )
                return parsed, confidence

        date_box = row.find("div", class_="dateBox")
        if date_box:
            text = date_box.get_text(" ", strip=True)
            match = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", text)
            if match:
                return self._parse_german_numeric_date(match.group(1)), FALLBACK_TIME

        return None, FALLBACK_TIME

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

    def _fetch_confirmed_datetime(
        self, client: Client | None, url: str
    ) -> datetime | None:
        """Fetch confirmed time from known first-party event detail pages."""
        if client is None or "kulturpalast-hannover.de/event/" not in url:
            return None

        try:
            response = client.get(url)
            response.raise_for_status()
        except Exception as exc:
            logger.debug("Failed to enrich Punkrock event time from %s: %s", url, exc)
            return None

        return self._parse_kulturpalast_datetime(response.text)

    def _parse_kulturpalast_datetime(self, html: str) -> datetime | None:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            match = re.search(r'"startDate"\s*:\s*"([^"]+)"', script.string)
            if not match:
                continue
            try:
                parsed = datetime.fromisoformat(match.group(1))
            except ValueError:
                continue
            if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
                return parsed.replace(tzinfo=BERLIN_TZ)
            return parsed.astimezone(BERLIN_TZ)

        return None
