"""First-party programme source for LUX Hannover."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import CONFIRMED_TIME
from boringhannover.genre import normalize_genre
from boringhannover.models import Event
from boringhannover.sanitize import (
    MAX_DESCRIPTION_LENGTH,
    MAX_TITLE_LENGTH,
    sanitize_text,
    sanitize_url,
)
from boringhannover.sources.base import BaseSource, create_http_client, register_source


if TYPE_CHECKING:
    from bs4 import Tag

__all__ = ["LuxSource"]

logger = logging.getLogger(__name__)


@register_source("lux")
class LuxSource(BaseSource):
    """Scrape concerts and club nights from the official LUX programme."""

    source_name: ClassVar[str] = "LUX"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 100

    URL: ClassVar[str] = "https://www.lux-linden.de/programm/"
    BASE_URL: ClassVar[str] = "https://www.lux-linden.de"
    ADDRESS: ClassVar[str] = "Schwarzer Bär 2, 30449 Hannover"
    MAX_FUTURE_DAYS: ClassVar[int] = 330
    _CANCELLED_MARKERS: ClassVar[tuple[str, ...]] = (
        "abgesagt",
        "entfällt",
        "ersatzlos gestrichen",
    )
    _DATE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.")
    _TIME_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")

    def fetch(self) -> list[Event]:
        """Fetch and parse the official LUX programme."""
        logger.info("Fetching events from %s", self.source_name)

        with create_http_client() as client:
            response = client.get(self.URL)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

        events = self._parse_events(soup)
        logger.info("Found %d events from %s", len(events), self.source_name)
        return events

    def _parse_events(
        self,
        soup: BeautifulSoup,
        *,
        now: datetime | None = None,
    ) -> list[Event]:
        """Parse unique, future programme cards."""
        reference = now or datetime.now(BERLIN_TZ)
        events: list[Event] = []
        seen: set[tuple[str, datetime]] = set()

        for card in soup.select(".event-listing-element.event"):
            event = self._parse_event(card, now=reference)
            if not event:
                continue

            key = (event.url, event.date)
            if key in seen:
                continue
            seen.add(key)
            events.append(event)

            if self.max_events and len(events) >= self.max_events:
                break

        return sorted(events, key=lambda event: event.date)

    def _parse_event(self, card: Tag, *, now: datetime) -> Event | None:
        """Parse one programme card, failing closed on incomplete timing."""
        fields = self._extract_info_fields(card)
        notice_text = self._extract_notice_text(card, fields).casefold()
        if any(marker in notice_text for marker in self._CANCELLED_MARKERS):
            return None

        title_element = card.select_one("h3.headline")
        if not title_element:
            return None
        title = sanitize_text(title_element.get_text(" ", strip=True), MAX_TITLE_LENGTH)
        if not title:
            return None

        link = title_element.find_parent("a")
        raw_url = str(link.get("href", "")).strip() if link else ""
        event_url = self._canonical_event_url(raw_url)
        if not event_url:
            return None

        event_date = self._parse_start(
            fields.get("am", ""), fields.get("beginn", ""), now
        )
        if not event_date:
            return None

        description = self._extract_description(card)
        event_type = "party" if "clubnight" in (card.get("class") or []) else "concert"
        metadata: dict[str, str | int | list[str]] = {
            "time": event_date.strftime("%H:%M"),
            "time_confidence": CONFIRMED_TIME,
            "event_type": event_type,
            "address": self.ADDRESS,
            "status": "sold_out" if "ausverkauft" in notice_text else "available",
        }

        if description:
            metadata["subtitle"] = description[:200]
            metadata["description"] = description

        image = card.select_one("img[src]")
        image_url = sanitize_url(str(image.get("src", ""))) if image else ""
        if image_url:
            metadata["image_url"] = image_url

        price = fields.get("vvk", "")
        if price and any(character.isdigit() for character in price):
            metadata["price"] = sanitize_text(price, 100)

        genre = normalize_genre(description)
        if genre:
            metadata["genre"] = genre
            metadata["genre_source"] = "programme_description"

        return Event(
            title=title,
            date=event_date,
            venue=self.source_name,
            url=event_url,
            category="radar",
            metadata=metadata,
        )

    def _extract_info_fields(self, card: Tag) -> dict[str, str]:
        fields: dict[str, str] = {}
        for row in card.select(".event-info-table > .row-fluid"):
            cells = row.find_all("div", recursive=False)
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True).casefold()
            value = cells[1].get_text(" ", strip=True)
            if label and value:
                fields[label] = value
        return fields

    def _extract_description(self, card: Tag) -> str:
        element = card.select_one(".container > .span6 .alt-font p")
        if not element:
            return ""
        text = element.get_text(" ", strip=True)
        text = re.sub(r"\s*…\s*weiter\s*$", "", text, flags=re.IGNORECASE)
        return sanitize_text(text, MAX_DESCRIPTION_LENGTH)

    def _extract_notice_text(self, card: Tag, fields: dict[str, str]) -> str:
        notices = [
            element.get_text(" ", strip=True) for element in card.select("h5.alt-font")
        ]
        notices.extend(fields.values())
        return " ".join(notices)

    def _parse_start(
        self,
        date_text: str,
        time_text: str,
        now: datetime,
    ) -> datetime | None:
        date_match = self._DATE_PATTERN.search(date_text)
        time_match = self._TIME_PATTERN.search(time_text)
        if not date_match or not time_match:
            return None

        day, month = (int(value) for value in date_match.groups())
        hour, minute = (int(value) for value in time_match.groups())
        try:
            candidate = datetime(
                now.year,
                month,
                day,
                hour,
                minute,
                tzinfo=BERLIN_TZ,
            )
            if candidate < now:
                candidate = candidate.replace(year=now.year + 1)
        except ValueError:
            return None

        if candidate > now + timedelta(days=self.MAX_FUTURE_DAYS):
            return None
        return candidate

    def _canonical_event_url(self, raw_url: str) -> str:
        url = sanitize_url(urljoin(self.BASE_URL, raw_url))
        if not url:
            return ""

        parsed = urlparse(url)
        if parsed.netloc.casefold() not in {"lux-linden.de", "www.lux-linden.de"}:
            return ""
        if not parsed.path.startswith(("/konzerte/", "/clubnight/")):
            return ""
        return url
