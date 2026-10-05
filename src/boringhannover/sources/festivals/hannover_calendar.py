"""Discovery-only source for official Hannover festival listings."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from boringhannover.constants import BERLIN_TZ, EVENT_LOOKAHEAD_DAYS
from boringhannover.models import Event
from boringhannover.occasions import OccasionDefinition
from boringhannover.sources.base import BaseSource, create_http_client, register_source


__all__ = ["HannoverFestivalCalendarSource"]

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

_DATE_PATTERN = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
_LOAD_MORE_PATH = re.compile(
    r"/api/v1/view/(?P<view>\d+)/(?P<offset>\d+)/(?P<limit>\d+)/(?P<format>[a-z]+)"
)
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
    MAX_LOAD_MORE_PAGES: ClassVar[int] = 10

    def fetch(self) -> list[Event]:
        """Return no timeline events; this source discovers parent occasions."""
        return []

    def discover_occasions(self) -> list[OccasionDefinition]:
        """Fetch and normalize the current official festival index."""
        with create_http_client() as client:
            html = self._fetch_calendar_html(client, self.CALENDAR_URL)
            occasions = [
                self._enrich_from_detail(client, occasion)
                if occasion.start_date == occasion.end_date or not occasion.location
                else occasion
                for occasion in self._parse_calendar(html)
            ]

        unlocated = [occasion.name for occasion in occasions if not occasion.location]
        if unlocated:
            logger.info("Skipped occasions without a location: %s", unlocated)
        occasions = [
            occasion for occasion in occasions if self._is_publishable(occasion)
        ]
        logger.info(
            "Discovered %d City Occasions from %s",
            len(occasions),
            self.source_name,
        )
        return occasions

    def _fetch_calendar_html(self, client: httpx.Client, url: str) -> str:
        """Return the first listing page plus every load-more page's cards.

        The listing renders ten cards; its "mehr" button pages through the
        rest via a JSON API. A failed later page keeps the cards already read.
        """
        response = client.get(url)
        response.raise_for_status()
        pages = [response.text]

        load_more = self._parse_load_more_request(response.text, str(response.url))
        next_url, params = load_more if load_more is not None else (None, {})
        for _ in range(self.MAX_LOAD_MORE_PAGES):
            if next_url is None:
                break
            try:
                response = client.get(next_url, params=params)
                response.raise_for_status()
                items_html, next_url = self._parse_load_more_page(
                    response.json(), str(response.url)
                )
            except Exception as exc:
                logger.warning(
                    "%s pagination stopped after %d pages: %s",
                    self.source_name,
                    len(pages),
                    exc,
                )
                break
            pages.append(items_html)
        else:
            if next_url is not None:
                logger.warning(
                    "%s listing truncated at %d pages",
                    self.source_name,
                    len(pages),
                )

        logger.info("Read %d listing pages from %s", len(pages), self.source_name)
        return "\n".join(pages)

    @classmethod
    def _parse_load_more_request(
        cls,
        html: str,
        page_url: str,
    ) -> tuple[str, dict[str, str]] | None:
        """Mirror the official "mehr" button's first load-more request."""
        button = BeautifulSoup(html, "html.parser").select_one(
            "button.more-items[data-tile_query]"
        )
        if button is None:
            return None

        url = cls._load_more_url(str(button.get("data-tile_query")), page_url)
        if url is None:
            logger.warning("Ignoring unexpected load-more URL on %s", page_url)
            return None

        params = {"identifiers": str(button.get("data-identi_query") or "")}
        sort_field = button.get("data-sort_field")
        sort_order = button.get("data-sort_order")
        if sort_field and sort_order:
            params |= {"sortField": str(sort_field), "sortOrder": str(sort_order)}
        return url, params

    @classmethod
    def _parse_load_more_page(
        cls,
        payload: object,
        page_url: str,
    ) -> tuple[str, str | None]:
        """Return a load-more page's card HTML and the next page URL, if any."""
        if not isinstance(payload, dict) or payload.get("success") is not True:
            msg = "Unsuccessful load-more response"
            raise ValueError(msg)

        items = payload.get("items")
        if not isinstance(items, list) or not all(
            isinstance(item, str) for item in items
        ):
            msg = "Malformed load-more items"
            raise ValueError(msg)

        html = "\n".join(items)
        raw_next = payload.get("next")
        if payload.get("isLast") is True or not isinstance(raw_next, str):
            return html, None

        next_url = cls._load_more_url(raw_next, page_url, continuation=True)
        if next_url is None:
            logger.warning(
                "%s pagination stopped at unexpected next URL %r",
                cls.source_name,
                raw_next,
            )
        return html, next_url

    @staticmethod
    def _load_more_url(
        raw_url: str,
        page_url: str,
        *,
        continuation: bool = False,
    ) -> str | None:
        """Resolve a load-more path on the same origin's view API.

        A continuation must stay on the current page's view, limit and format;
        only the offset may change.
        """
        url = urljoin(page_url, raw_url.strip())
        parsed, page = urlparse(url), urlparse(page_url)
        if (parsed.scheme, parsed.netloc) != (page.scheme, page.netloc):
            return None
        match = _LOAD_MORE_PATH.fullmatch(parsed.path)
        if match is None:
            return None
        if continuation:
            current = _LOAD_MORE_PATH.fullmatch(page.path)
            view = ("view", "limit", "format")
            if current is None or current.group(*view) != match.group(*view):
                return None
        return parsed._replace(query="", fragment="").geturl()

    def _parse_calendar(self, html: str) -> list[OccasionDefinition]:
        """Parse stable line-view event cards from the official calendar.

        Cards without a listing location are kept with an empty location so
        detail enrichment can read the official Ort row.
        """
        soup = BeautifulSoup(html, "html.parser")
        occasions: dict[str, OccasionDefinition] = {}

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
            occasions.setdefault(
                f"hannover-festivals:{slug}",
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
                ),
            )

        return sorted(
            occasions.values(),
            key=lambda occasion: (occasion.start_date, occasion.name),
        )

    def _enrich_from_detail(
        self,
        client: httpx.Client,
        occasion: OccasionDefinition,
    ) -> OccasionDefinition:
        """Read detail rows for near-term one-day or location-less summaries."""
        today = datetime.now(BERLIN_TZ).date()
        if occasion.start_date > today + timedelta(days=EVENT_LOOKAHEAD_DAYS):
            return occasion

        try:
            response = client.get(occasion.source_url)
            response.raise_for_status()
        except Exception as exc:
            logger.warning(
                "Could not read occasion details for %s: %s",
                occasion.source_url,
                exc,
            )
            return occasion
        return self._apply_detail(occasion, response.text)

    @classmethod
    def _apply_detail(
        cls,
        occasion: OccasionDefinition,
        html: str,
    ) -> OccasionDefinition:
        """Extend the end date and fill a missing location from detail rows."""
        end_date = cls._parse_detail_end_date(html)
        return replace(
            occasion,
            end_date=max(occasion.end_date, end_date or occasion.end_date),
            location=occasion.location or cls._parse_detail_location(html),
        )

    @classmethod
    def _parse_detail_end_date(cls, html: str) -> date | None:
        """Return the final date from the official detail-page Termine row."""
        cell = cls._detail_cell(html, "termine")
        parsed = cls._parse_dates(cls._text(cell)) if cell is not None else None
        return parsed[-1] if parsed is not None else None

    @classmethod
    def _parse_detail_location(cls, html: str) -> str:
        """Return the official detail-page Ort row as one address line."""
        cell = cls._detail_cell(html, "ort")
        if cell is None:
            return ""
        for line_break in cell.find_all("br"):
            line_break.replace_with("\n")
        lines = (" ".join(line.split()) for line in cell.get_text(" ").split("\n"))
        return ", ".join(line for line in lines if line)

    @classmethod
    def _detail_cell(cls, html: str, label: str) -> Tag | None:
        """Return the value cell of a labelled official detail row."""
        soup = BeautifulSoup(html, "html.parser")
        for row in soup.select(".details .detail-row"):
            cells = row.select(".detail-cell")
            if len(cells) >= 2 and cls._text(cells[0]).casefold() == label:
                return cells[1]
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

    @classmethod
    def _is_publishable(cls, occasion: OccasionDefinition) -> bool:
        """Require a known location inside the city after detail enrichment."""
        return bool(occasion.location) and not cls._is_outside_city(
            f"{occasion.name} {occasion.location} {occasion.description}"
        )

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
