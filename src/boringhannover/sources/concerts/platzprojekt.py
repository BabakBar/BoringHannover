"""Platzprojekt events source using its public calendar REST API."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, ClassVar, cast
from urllib.parse import urlparse

from boringhannover.constants import BERLIN_TZ, EVENT_LOOKAHEAD_DAYS
from boringhannover.event_time import CONFIRMED_TIME, FALLBACK_TIME
from boringhannover.models import Event
from boringhannover.sanitize import sanitize_text, sanitize_url
from boringhannover.sources.base import BaseSource, create_http_client, register_source


if TYPE_CHECKING:
    import httpx

__all__ = ["PlatzprojektSource"]

logger = logging.getLogger(__name__)


@register_source("platzprojekt")
class PlatzprojektSource(BaseSource):
    """Fetch public events from Platzprojekt's official WordPress calendar."""

    source_name: ClassVar[str] = "PLATZprojekt"
    source_type: ClassVar[str] = "event"
    max_events: ClassVar[int | None] = 100

    API_URL: ClassVar[str] = "https://platzprojekt.de/wp-json/tribe/events/v1/events"
    ADDRESS: ClassVar[str] = "Fössestraße 103, 30453 Hannover"
    FALLBACK_HOUR: ClassVar[int] = 12

    _CANCELLATION_MARKERS: ClassVar[tuple[str, ...]] = (
        "fällt aus",
        "faellt aus",
        "abgesagt",
        "cancelled",
        "canceled",
    )

    def fetch(self) -> list[Event]:
        """Fetch events inside the shared aggregation horizon."""
        now = datetime.now(BERLIN_TZ)
        cutoff = now + timedelta(days=EVENT_LOOKAHEAD_DAYS)

        with create_http_client() as client:
            events = self._fetch_pages(client, now, cutoff)

        events.sort(key=lambda event: event.date)
        if self.max_events is not None:
            events = events[: self.max_events]
        logger.info("Found %d events from %s", len(events), self.source_name)
        return events

    def _fetch_pages(
        self,
        client: httpx.Client,
        now: datetime,
        cutoff: datetime,
    ) -> list[Event]:
        events: list[Event] = []
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = client.get(
                self.API_URL,
                params={
                    "start_date": now.strftime("%Y-%m-%d"),
                    "end_date": cutoff.strftime("%Y-%m-%d"),
                    "per_page": "50",
                    "page": str(page),
                },
            )
            response.raise_for_status()
            payload = response.json()
            events.extend(self._parse_payload(payload, now=now))
            total_pages = self._total_pages(payload)
            page += 1

        return events

    def _parse_payload(
        self,
        payload: object,
        *,
        now: datetime,
    ) -> list[Event]:
        """Parse one page from The Events Calendar API."""
        if not isinstance(payload, dict):
            return []

        page = cast("dict[str, object]", payload)
        raw_events = page.get("events")
        if not isinstance(raw_events, list):
            return []

        events: list[Event] = []
        for raw_event in raw_events:
            if not isinstance(raw_event, dict):
                continue
            event = self._parse_event(cast("dict[str, object]", raw_event), now)
            if event is not None:
                events.append(event)
        return sorted(events, key=lambda event: event.date)

    def _parse_event(
        self,
        data: dict[str, object],
        now: datetime,
    ) -> Event | None:
        if data.get("status") != "publish" or data.get("hide_from_listings") is True:
            return None

        raw_title = data.get("title")
        raw_start = data.get("start_date")
        raw_url = data.get("url")
        if not all(isinstance(value, str) for value in (raw_title, raw_start, raw_url)):
            return None

        title = sanitize_text(cast("str", raw_title), 200)
        url = sanitize_url(cast("str", raw_url))
        if (
            not title
            or self._is_cancelled(title)
            or not self._is_canonical_event_url(url)
        ):
            return None

        event_date = self._parse_datetime(cast("str", raw_start))
        if event_date is None:
            return None

        all_day = data.get("all_day") is True
        if all_day:
            if event_date.date() < now.date():
                return None
            event_date = event_date.replace(hour=self.FALLBACK_HOUR)
            time_confidence = FALLBACK_TIME
        else:
            if event_date < now:
                return None
            time_confidence = CONFIRMED_TIME

        venue, address = self._parse_venue(data.get("venue"))
        raw_description = data.get("description")
        description = sanitize_text(
            raw_description if isinstance(raw_description, str) else "",
            200,
        )
        image_url = self._parse_image_url(data.get("image"))
        raw_cost = data.get("cost")
        price = sanitize_text(
            raw_cost if isinstance(raw_cost, str) else "",
            100,
        )
        end_time = "" if all_day else self._parse_end_time(data.get("end_date"))

        return Event(
            title=title,
            date=event_date,
            venue=venue,
            url=url,
            category="radar",
            metadata={
                "time": event_date.strftime("%H:%M"),
                "time_confidence": time_confidence,
                "end_time": end_time,
                "event_type": "event",
                "subtitle": description,
                "description": description,
                "image_url": image_url,
                "address": address,
                "price": price,
                "source_name": self.source_name,
            },
        )

    def _parse_venue(self, raw_venue: object) -> tuple[str, str]:
        if not isinstance(raw_venue, dict):
            return self.source_name, self.ADDRESS

        venue_data = cast("dict[str, object]", raw_venue)
        raw_name = venue_data.get("venue")
        venue = sanitize_text(
            raw_name if isinstance(raw_name, str) else "",
            100,
        )
        raw_street = venue_data.get("address")
        street = sanitize_text(
            raw_street if isinstance(raw_street, str) else "",
            100,
        )
        raw_postal_code = venue_data.get("zip")
        postal_code = sanitize_text(
            raw_postal_code if isinstance(raw_postal_code, str) else "",
            20,
        )
        raw_city = venue_data.get("city")
        city = sanitize_text(
            raw_city if isinstance(raw_city, str) else "",
            100,
        )
        locality = " ".join(part for part in (postal_code, city) if part)
        address = ", ".join(part for part in (street, locality) if part)
        return venue or self.source_name, address or self.ADDRESS

    def _parse_image_url(self, raw_image: object) -> str:
        if not isinstance(raw_image, dict):
            return ""
        image = cast("dict[str, object]", raw_image)
        raw_url = image.get("url")
        return sanitize_url(raw_url) if isinstance(raw_url, str) else ""

    def _parse_end_time(self, raw_end: object) -> str:
        if not isinstance(raw_end, str):
            return ""
        end = self._parse_datetime(raw_end)
        return end.strftime("%H:%M") if end is not None else ""

    def _parse_datetime(self, raw_date: str) -> datetime | None:
        try:
            return datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=BERLIN_TZ
            )
        except ValueError:
            return None

    def _is_cancelled(self, title: str) -> bool:
        normalized = title.casefold()
        return any(marker in normalized for marker in self._CANCELLATION_MARKERS)

    def _is_canonical_event_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in {"platzprojekt.de", "www.platzprojekt.de"}
            and parsed.path.startswith("/programm/")
            and parsed.path != "/programm/"
        )

    def _total_pages(self, payload: object) -> int:
        if not isinstance(payload, dict):
            return 1
        page = cast("dict[str, object]", payload)
        raw_total = page.get("total_pages")
        if isinstance(raw_total, int):
            return max(1, raw_total)
        return 1
