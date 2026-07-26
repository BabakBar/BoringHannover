"""Seasonal source for the official Maschseefest 2026 programme."""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, replace
from datetime import date as date_type
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, ClassVar, cast
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from boringhannover.constants import BERLIN_TZ, EVENT_LOOKAHEAD_DAYS
from boringhannover.event_time import CONFIRMED_TIME, FALLBACK_TIME
from boringhannover.models import Event
from boringhannover.occasions import OccasionDefinition, classify_programme_item
from boringhannover.sources.base import BaseSource, create_http_client, register_source


if TYPE_CHECKING:
    import httpx
    from bs4 import Tag

__all__ = ["MaschseefestSource"]

logger = logging.getLogger(__name__)

_DATE_PATTERN = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
_TIME_PATTERN = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")


@dataclass(frozen=True, slots=True)
class _ProgrammeEntry:
    """Programme data collected from a listing card or detail page."""

    url: str
    title: str | None = None
    date: date_type | None = None
    start_time: str | None = None
    end_time: str | None = None
    venue: str | None = None
    description: str | None = None
    image_url: str | None = None


@register_source("maschseefest")
class MaschseefestSource(BaseSource):
    """Fetch the official Maschseefest 2026 programme.

    WordPress REST provides the canonical event inventory, while the rendered
    programme contains the public Jet Engine fields. Individual detail pages
    are requested only when a within-horizon programme card lacks a confirmed
    start time or concrete location.
    """

    source_name: ClassVar[str] = "Maschseefest"
    source_type: ClassVar[str] = "festival"
    enabled: ClassVar[bool] = True
    max_events: ClassVar[int | None] = None

    BASE_URL: ClassVar[str] = "https://www.maschseefest.de"
    PROGRAMME_URL: ClassVar[str] = f"{BASE_URL}/veranstaltungen/"
    REST_URL: ClassVar[str] = f"{BASE_URL}/wp-json/wp/v2/cpt_veranstaltungen"
    SEASON_START: ClassVar[date_type] = date_type(2026, 7, 22)
    SEASON_END: ClassVar[date_type] = date_type(2026, 8, 9)
    FALLBACK_START_TIME: ClassVar[time] = time(12, 0)
    occasion: ClassVar[OccasionDefinition | None] = OccasionDefinition(
        id="maschseefest-2026",
        slug="maschseefest-2026",
        name="Maschseefest",
        kind="festival",
        start_date=SEASON_START,
        end_date=SEASON_END,
        location="Around the Maschsee",
        source_url=PROGRAMME_URL,
        description=(
            "Music, food, family moments and late nights around Hannover's lake."
        ),
    )

    def fetch(self) -> list[Event]:
        """Fetch events in the aggregation horizon during the 2026 season."""
        now = datetime.now(BERLIN_TZ)
        if not self._is_active(now.date()):
            logger.info("%s is outside its active 2026 season", self.source_name)
            return []

        cutoff = now + timedelta(days=EVENT_LOOKAHEAD_DAYS)
        with create_http_client() as client:
            inventory = self._fetch_inventory(client)
            if not inventory:
                logger.warning("%s REST inventory is empty", self.source_name)
                return []

            events = self._fetch_programme(client, inventory, now, cutoff)

        events.sort(key=lambda event: event.date)
        logger.info("Found %d events from %s", len(events), self.source_name)
        return events

    def _is_active(self, today: date_type) -> bool:
        """Return whether the source can contribute to the current horizon."""
        active_from = self.SEASON_START - timedelta(days=EVENT_LOOKAHEAD_DAYS)
        return active_from <= today <= self.SEASON_END

    def _fetch_inventory(self, client: httpx.Client) -> dict[str, str]:
        """Fetch every canonical event URL from the paginated REST endpoint."""
        inventory: dict[str, str] = {}
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = client.get(
                self.REST_URL,
                params={
                    "per_page": "100",
                    "page": str(page),
                    "_fields": "id,title,link",
                },
            )
            response.raise_for_status()
            inventory.update(self._parse_inventory(response.json()))

            raw_total_pages = response.headers.get("X-WP-TotalPages", "1")
            try:
                total_pages = max(1, int(raw_total_pages))
            except ValueError:
                logger.warning(
                    "%s returned invalid X-WP-TotalPages=%r",
                    self.source_name,
                    raw_total_pages,
                )
                total_pages = page
            page += 1

        return inventory

    def _parse_inventory(self, payload: object) -> dict[str, str]:
        """Parse and validate a WordPress REST inventory page."""
        if not isinstance(payload, list):
            return {}

        inventory: dict[str, str] = {}
        for raw_item in payload:
            if not isinstance(raw_item, dict):
                continue

            item = cast("dict[str, object]", raw_item)
            raw_url = item.get("link")
            raw_title = item.get("title")
            if not isinstance(raw_url, str) or not isinstance(raw_title, dict):
                continue

            title_data = cast("dict[str, object]", raw_title)
            rendered_title = title_data.get("rendered")
            if not isinstance(rendered_title, str):
                continue

            url = raw_url.strip()
            title = self._clean_text(html.unescape(rendered_title))
            if self._is_canonical_event_url(url) and title:
                inventory[url] = title

        return inventory

    def _fetch_programme(
        self,
        client: httpx.Client,
        inventory: dict[str, str],
        now: datetime,
        cutoff: datetime,
    ) -> list[Event]:
        """Fetch sorted programme pages and enrich incomplete cards."""
        events: list[Event] = []
        seen_urls: set[str] = set()
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = client.get(
                self.PROGRAMME_URL,
                params={"jsf": "jet-engine:default", "pagenum": str(page)},
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            entries, parsed_total_pages = self._parse_programme_page(soup, inventory)
            total_pages = max(total_pages, parsed_total_pages)

            dated_entries = [entry for entry in entries if entry.date is not None]
            for entry in dated_entries:
                if entry.url in seen_urls:
                    continue

                event_day = entry.date
                if event_day is None or not (now.date() <= event_day <= cutoff.date()):
                    continue

                if self._needs_detail(entry):
                    entry = self._fetch_detail(client, entry)

                event = self._to_event(entry)
                if now <= event.date <= cutoff:
                    events.append(event)
                    seen_urls.add(entry.url)

            if dated_entries and all(
                entry.date is not None and entry.date > cutoff.date()
                for entry in dated_entries
            ):
                break
            page += 1

        return events

    def _parse_programme_page(
        self,
        soup: BeautifulSoup,
        inventory: dict[str, str],
    ) -> tuple[list[_ProgrammeEntry], int]:
        """Parse one server-rendered Jet Engine programme page."""
        grid = soup.select_one(".jet-listing-grid__items[data-pages]")
        if grid is None:
            return [], 1

        try:
            total_pages = max(1, int(str(grid.get("data-pages", "1"))))
        except ValueError:
            total_pages = 1

        entries: list[_ProgrammeEntry] = []
        for card in grid.find_all(
            "div",
            class_="jet-listing-grid__item",
            recursive=False,
        ):
            entry = self._parse_programme_card(card, inventory)
            if entry is not None:
                entries.append(entry)

        return entries, total_pages

    def _parse_programme_card(
        self,
        card: Tag,
        inventory: dict[str, str],
    ) -> _ProgrammeEntry | None:
        """Parse one rendered programme card."""
        link = card.select_one("a.jet-engine-listing-overlay-link[href]")
        raw_url = link.get("href") if link is not None else None
        if not isinstance(raw_url, str):
            return None

        url = raw_url.strip()
        inventory_title = inventory.get(url)
        if inventory_title is None:
            return None

        card_title = self._select_text(
            card,
            ".elementor-element-1379868 .elementor-heading-title",
        )
        return _ProgrammeEntry(
            url=url,
            title=card_title or inventory_title,
            date=self._parse_date(
                self._select_text(
                    card,
                    ".elementor-element-60f4b76 .jet-listing-dynamic-field__content",
                )
            ),
            start_time=self._parse_time(
                self._select_text(
                    card,
                    ".elementor-element-c2c8a7a .jet-listing-dynamic-field__content",
                )
            ),
            end_time=self._parse_time(
                self._select_text(
                    card,
                    ".elementor-element-4b78487 .jet-listing-dynamic-field__content",
                )
            ),
            venue=self._select_text(
                card,
                ".elementor-element-88bae22 .jet-listing-dynamic-field__content",
            ),
            description=self._select_text(
                card,
                ".elementor-element-5262e44 .elementor-widget-container",
            ),
            image_url=self._select_image_url(
                card,
                ".elementor-element-e34e537 img[src]",
            ),
        )

    def _needs_detail(self, entry: _ProgrammeEntry) -> bool:
        """Return whether a programme card needs bounded detail enrichment."""
        return entry.start_time is None or entry.venue is None

    def _fetch_detail(
        self,
        client: httpx.Client,
        entry: _ProgrammeEntry,
    ) -> _ProgrammeEntry:
        """Fetch one detail page, preserving usable listing data on failure."""
        try:
            response = client.get(entry.url)
            response.raise_for_status()
            detail = self._parse_detail_page(
                BeautifulSoup(response.text, "html.parser")
            )
            return self._enrich_entry(entry, detail)
        except Exception as exc:
            logger.warning("Failed to enrich %s: %s", entry.url, exc)
            return entry

    def _parse_detail_page(self, soup: BeautifulSoup) -> _ProgrammeEntry:
        """Parse the public Jet Engine fields from an event detail page."""
        return _ProgrammeEntry(
            url="",
            title=self._select_text(
                soup,
                ".elementor-element-63ec074 .elementor-heading-title",
            ),
            date=self._parse_date(
                self._select_text(
                    soup,
                    ".elementor-element-c275d9a .jet-listing-dynamic-field__content",
                )
            ),
            start_time=self._parse_time(
                self._select_text(
                    soup,
                    ".elementor-element-3a82767 .jet-listing-dynamic-field__content",
                )
            ),
            end_time=self._parse_time(
                self._select_text(
                    soup,
                    ".elementor-element-1d7ce41 .jet-listing-dynamic-field__content",
                )
            ),
            venue=self._select_text(
                soup,
                ".elementor-element-eda8d5c .jet-listing-dynamic-field__content",
            ),
            description=self._select_text(
                soup,
                ".elementor-element-2b4f333 .elementor-widget-container",
            ),
            image_url=self._select_image_url(
                soup,
                ".elementor-element-9b4c242 img[src]",
            ),
        )

    @staticmethod
    def _enrich_entry(
        entry: _ProgrammeEntry,
        detail: _ProgrammeEntry,
    ) -> _ProgrammeEntry:
        """Fill missing listing fields from a parsed detail page."""
        return replace(
            entry,
            title=detail.title or entry.title,
            date=detail.date or entry.date,
            start_time=detail.start_time or entry.start_time,
            end_time=detail.end_time or entry.end_time,
            venue=detail.venue or entry.venue,
            description=detail.description or entry.description,
            image_url=detail.image_url or entry.image_url,
        )

    def _to_event(self, entry: _ProgrammeEntry) -> Event:
        """Convert a parsed programme entry to the shared event model."""
        if entry.date is None or entry.title is None:
            msg = f"Incomplete Maschseefest entry: {entry.url}"
            raise ValueError(msg)

        start_time = self._time_value(entry.start_time) or self.FALLBACK_START_TIME
        time_confidence = (
            CONFIRMED_TIME if entry.start_time is not None else FALLBACK_TIME
        )
        description = entry.description or ""
        programme_category = classify_programme_item(entry.title, description)

        return Event(
            title=entry.title,
            date=datetime.combine(entry.date, start_time, tzinfo=BERLIN_TZ),
            venue=entry.venue or self.source_name,
            url=entry.url,
            category="radar",
            metadata={
                "time": entry.start_time or self.FALLBACK_START_TIME.strftime("%H:%M"),
                "time_confidence": time_confidence,
                "end_time": entry.end_time or "",
                "event_type": "festival",
                "occasion_id": "maschseefest-2026",
                "programme_category": programme_category or "",
                "subtitle": description,
                "description": description,
                "image_url": entry.image_url or "",
            },
        )

    def _is_canonical_event_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in {"maschseefest.de", "www.maschseefest.de"}
            and parsed.path.startswith("/veranstaltungen/")
            and parsed.path != "/veranstaltungen/"
        )

    @staticmethod
    def _select_text(root: BeautifulSoup | Tag, selector: str) -> str | None:
        element = root.select_one(selector)
        if element is None:
            return None
        return MaschseefestSource._clean_text(element.get_text(" ", strip=True))

    @staticmethod
    def _select_image_url(
        root: BeautifulSoup | Tag,
        selector: str,
    ) -> str | None:
        image = root.select_one(selector)
        raw_url = image.get("src") if image is not None else None
        if not isinstance(raw_url, str):
            return None
        url = raw_url.strip()
        return url if url.startswith("https://") else None

    @staticmethod
    def _parse_date(value: str | None) -> date_type | None:
        if value is None:
            return None
        match = _DATE_PATTERN.search(value)
        if match is None:
            return None
        day, month, year = match.groups()
        try:
            return date_type(int(year), int(month), int(day))
        except ValueError:
            return None

    @staticmethod
    def _parse_time(value: str | None) -> str | None:
        if value is None:
            return None
        match = _TIME_PATTERN.search(value)
        if match is None:
            return None
        hour, minute = match.groups()
        return f"{int(hour):02d}:{minute}"

    @staticmethod
    def _time_value(value: str | None) -> time | None:
        parsed = MaschseefestSource._parse_time(value)
        if parsed is None:
            return None
        hour, minute = parsed.split(":")
        return time(int(hour), int(minute))

    @staticmethod
    def _clean_text(value: str) -> str:
        return " ".join(value.split()).strip()
