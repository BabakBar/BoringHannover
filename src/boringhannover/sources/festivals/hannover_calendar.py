"""Discovery-only source for official Hannover festival listings."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from boringhannover.constants import BERLIN_TZ, EVENT_LOOKAHEAD_DAYS
from boringhannover.models import Event
from boringhannover.occasions import OccasionDefinition
from boringhannover.sources.base import BaseSource, create_http_client, register_source


__all__ = ["HannoverFestivalCalendarSource"]

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

_DATE_PATTERN = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
_OUTSIDE_CITY_MARKERS = (
    "langenhagen",
    "pattensen",
    "poggenhagen",
    "region hannover",
    "springe",
    "völksen",
    "wennigsen",
)


@register_source("hannover_festival_calendar")
class HannoverFestivalCalendarSource(BaseSource):
    """Discover summary-only occasions from Hannover's official calendar."""

    source_name: ClassVar[str] = "Hannover Festival Calendar"
    source_type: ClassVar[str] = "occasion"
    enabled: ClassVar[bool] = True
    max_events: ClassVar[int | None] = None

    BASE_URL: ClassVar[str] = "https://www.hannover.de"
    CALENDAR_URL: ClassVar[str] = f"{BASE_URL}/Veranstaltungskalender/Feste-Festivals"

    def fetch(self) -> list[Event]:
        """Return no timeline events; this source discovers parent occasions."""
        return []

    def discover_occasions(self) -> list[OccasionDefinition]:
        """Fetch and normalize the current official festival index."""
        with create_http_client() as client:
            response = client.get(self.CALENDAR_URL)
            response.raise_for_status()
            occasions = self._parse_calendar(response.text)
            occasions = [
                self._enrich_end_date(client, occasion)
                if occasion.start_date == occasion.end_date
                else occasion
                for occasion in occasions
            ]

        logger.info(
            "Discovered %d City Occasions from %s",
            len(occasions),
            self.source_name,
        )
        return occasions

    def _parse_calendar(self, html: str) -> list[OccasionDefinition]:
        """Parse stable line-view event cards from the official calendar."""
        soup = BeautifulSoup(html, "html.parser")
        occasions: list[OccasionDefinition] = []

        for card in soup.select("article.interesting-single.line-view-content"):
            title = self._text(card.select_one(".interesting-single__title"))
            dates = self._parse_dates(self._text(card.select_one(".date__duration")))
            location = self._text(card.select_one(".date__category"))
            description = self._text(
                card.select_one(".interesting-single__description p")
            )
            link = card.select_one("a.content__read-more[href]")
            raw_href = link.get("href") if link is not None else None

            if (
                not title
                or dates is None
                or not location
                or not isinstance(raw_href, str)
                or self._is_outside_city(f"{title} {location} {description}")
            ):
                continue

            source_url = urljoin(self.BASE_URL, raw_href.strip())
            if not self._is_official_url(source_url):
                continue

            slug = self._slug_from_url(source_url)
            if not slug:
                continue

            image = card.select_one("img")
            image_url = ""
            if image is not None:
                raw_image = image.get("data-large-image") or image.get("src")
                if isinstance(raw_image, str):
                    image_url = urljoin(self.BASE_URL, raw_image.strip())

            start_date, end_date = dates
            occasions.append(
                OccasionDefinition(
                    id=f"hannover-festivals:{slug}",
                    slug=slug,
                    name=title,
                    kind="festival",
                    start_date=start_date,
                    end_date=end_date,
                    location=location,
                    source_url=source_url,
                    description=description or f"{title} in Hannover.",
                    image_url=image_url,
                )
            )

        occasions.sort(key=lambda occasion: (occasion.start_date, occasion.name))
        return occasions

    def _enrich_end_date(
        self,
        client: httpx.Client,
        occasion: OccasionDefinition,
    ) -> OccasionDefinition:
        """Read multi-date detail rows for near-term one-day summaries."""
        today = datetime.now(BERLIN_TZ).date()
        if occasion.start_date > today + timedelta(days=EVENT_LOOKAHEAD_DAYS):
            return occasion

        try:
            response = client.get(occasion.source_url)
            response.raise_for_status()
            end_date = self._parse_detail_end_date(response.text)
        except Exception as exc:
            logger.warning(
                "Could not enrich occasion dates for %s: %s",
                occasion.source_url,
                exc,
            )
            return occasion

        if end_date is None or end_date <= occasion.end_date:
            return occasion
        return replace(occasion, end_date=end_date)

    @staticmethod
    def _parse_detail_end_date(html: str) -> date | None:
        """Return the final date from the official detail-page Termine row."""
        soup = BeautifulSoup(html, "html.parser")
        for row in soup.select(".details .detail-row"):
            cells = row.select(".detail-cell")
            if len(cells) < 2:
                continue
            if HannoverFestivalCalendarSource._text(cells[0]).casefold() != "termine":
                continue

            parsed = HannoverFestivalCalendarSource._parse_dates(
                HannoverFestivalCalendarSource._text(cells[1])
            )
            return parsed[-1] if parsed is not None else None
        return None

    @staticmethod
    def _parse_dates(value: str) -> tuple[date, date] | None:
        matches = _DATE_PATTERN.findall(value)
        if not matches:
            return None

        try:
            parsed = [
                date(int(year), int(month), int(day)) for day, month, year in matches
            ]
        except ValueError:
            return None

        return parsed[0], parsed[-1]

    @staticmethod
    def _text(element: object) -> str:
        get_text = getattr(element, "get_text", None)
        if not callable(get_text):
            return ""
        return " ".join(str(get_text(" ", strip=True)).split())

    @staticmethod
    def _is_outside_city(location: str) -> bool:
        normalized = location.casefold()
        return any(marker in normalized for marker in _OUTSIDE_CITY_MARKERS)

    @staticmethod
    def _is_official_url(url: str) -> bool:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in {"hannover.de", "www.hannover.de"}
            and parsed.path.startswith("/Veranstaltungskalender/")
        )

    @staticmethod
    def _slug_from_url(url: str) -> str:
        path_name = urlparse(url).path.rstrip("/").rsplit("/", maxsplit=1)[-1]
        ascii_name = (
            unicodedata.normalize("NFKD", path_name)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        return re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
