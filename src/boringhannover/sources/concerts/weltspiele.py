"""Weltspiele (Weidendamm) Hannover source.

Fetches upcoming events from the Weltspiele club program.
Program list provides day/month and tags; event pages provide time.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from boringhannover.config import GERMAN_MONTH_MAP
from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sources.base import BaseSource, create_http_client, register_source


__all__ = ["WeltspieleSource"]

logger = logging.getLogger(__name__)


ENGLISH_MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass(frozen=True)
class _ProgramEntry:
    title: str
    day: int
    month: int
    url: str
    tag: str | None
    lineup: str | None


@register_source("weltspiele")
class WeltspieleSource(BaseSource):
    """Scraper for Weltspiele Club (Weidendamm 8) in Hannover.

    Website: https://weltspiele.club/programm/

    Attributes:
        source_name: "Weltspiele"
        source_type: "concert"
    """

    source_name: ClassVar[str] = "Weltspiele"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 30

    PROGRAM_URL: ClassVar[str] = "https://weltspiele.club/programm/"
    BASE_URL: ClassVar[str] = "https://weltspiele.club"
    ADDRESS: ClassVar[str] = "Weidendamm 8, 30167 Hannover"

    SELECTOR_MONTH: ClassVar[str] = "div.program-month"
    SELECTOR_MONTH_TITLE: ClassVar[str] = ".program-month-title"
    SELECTOR_EVENT: ClassVar[str] = "li.program-event"
    SELECTOR_DAY: ClassVar[str] = ".program-event-header .in-brackets"
    SELECTOR_TAG: ClassVar[str] = ".program-event-tag"
    SELECTOR_TITLE: ClassVar[str] = "div.underline"
    SELECTOR_LINEUP: ClassVar[str] = ".program-event-place .underline-rich-text-box"
    SELECTOR_SHOW_DATE: ClassVar[str] = ".show-date"
    SELECTOR_EVENT_TITLE: ClassVar[str] = "h1.event-title"

    def fetch(self) -> list[Event]:
        """Fetch club events from Weltspiele.

        Returns:
            List of Event objects with category="radar".
        """
        logger.info("Fetching concerts from %s", self.source_name)

        with create_http_client() as client:
            response = client.get(self.PROGRAM_URL)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            program_entries = self._parse_program(soup)

            events: list[Event] = []
            for entry in program_entries:
                event = self._build_event(client, entry)
                if event:
                    events.append(event)
                    if self.max_events and len(events) >= self.max_events:
                        break

        logger.info("Found %d events from %s", len(events), self.source_name)
        return events

    def _parse_program(self, soup: BeautifulSoup) -> list[_ProgramEntry]:
        """Parse the program overview page into entries."""
        entries: list[_ProgramEntry] = []
        for month_block in soup.select(self.SELECTOR_MONTH):
            month_title = month_block.select_one(self.SELECTOR_MONTH_TITLE)
            month_name = month_title.get_text(strip=True) if month_title else ""
            month_num = self._parse_month(month_name)
            if not month_num:
                continue

            for item in month_block.select(self.SELECTOR_EVENT):
                entry = self._parse_program_event(item, month_num)
                if entry:
                    entries.append(entry)
        return entries

    def _parse_program_event(self, item: Tag, month_num: int) -> _ProgramEntry | None:
        link = item.find_parent("a", href=True)
        url = str(link.get("href", "")).strip() if link else ""
        if not url:
            return None
        if url.startswith("/"):
            url = f"{self.BASE_URL}{url}"

        day_elem = item.select_one(self.SELECTOR_DAY)
        day_text = day_elem.get_text(" ", strip=True) if day_elem else ""
        day_match = re.search(r"(\d{1,2})", day_text)
        if not day_match:
            return None
        day = int(day_match.group(1))

        title = self._extract_title(item)
        if not title:
            return None

        tag_elem = item.select_one(self.SELECTOR_TAG)
        tag = tag_elem.get_text(strip=True) if tag_elem else None

        lineup = self._extract_lineup(item)

        return _ProgramEntry(
            title=title,
            day=day,
            month=month_num,
            url=url,
            tag=tag,
            lineup=lineup,
        )

    def _extract_title(self, item: Tag) -> str:
        candidates = item.select(self.SELECTOR_TITLE)
        for candidate in candidates:
            classes = candidate.get("class") or []
            if "underline-rich-text-box" in classes:
                continue
            title = candidate.get_text(strip=True)
            if title:
                return title
        return ""

    def _extract_lineup(self, item: Tag) -> str | None:
        blocks = item.select(self.SELECTOR_LINEUP)
        if not blocks:
            return None
        text = " ".join(block.get_text(" ", strip=True) for block in blocks)
        text = " ".join(text.split())
        return text or None

    def _build_event(self, client, entry: _ProgramEntry) -> Event | None:
        event_date = self._compose_date(entry.day, entry.month)
        if not event_date:
            return None

        time_str = None
        page_title = None
        show_date, page_title, page_ok = self._fetch_event_page(client, entry.url)
        if show_date:
            parsed = self._parse_show_date(show_date)
            if parsed:
                event_date = parsed
                time_str = event_date.strftime("%H:%M")

        if not time_str:
            time_str = "22:00"
            event_date = event_date.replace(hour=22, minute=0)

        title = page_title or entry.title

        event_url = entry.url if page_ok else self.PROGRAM_URL

        return Event(
            title=title,
            date=event_date,
            venue=self.source_name,
            url=event_url,
            category="radar",
            metadata={
                "time": time_str,
                "subtitle": entry.lineup[:200] if entry.lineup else "",
                "event_type": entry.tag or "club",
                "address": self.ADDRESS,
            },
        )

    def _fetch_event_page(
        self, client, url: str
    ) -> tuple[str | None, str | None, bool]:
        response = client.get(url)
        page_ok = response.status_code < 400
        if not page_ok:
            logger.debug(
                "Weltspiele event page returned %d: %s", response.status_code, url
            )
        soup = BeautifulSoup(response.text, "html.parser")

        show_date_elem = soup.select_one(self.SELECTOR_SHOW_DATE)
        show_date = show_date_elem.get_text(" ", strip=True) if show_date_elem else None

        title_elem = soup.select_one(self.SELECTOR_EVENT_TITLE)
        title = title_elem.get_text(strip=True) if title_elem else None
        return show_date, title or None, page_ok

    def _parse_show_date(self, text: str) -> datetime | None:
        """Parse show-date string like 'Sat 27 January 22:00-10:00'."""
        if not text:
            return None

        time_match = re.search(r"(\d{1,2}:\d{2})", text)
        if not time_match:
            return None
        time_str = time_match.group(1)

        date_match = re.search(r"(\d{1,2})\s+([A-Za-zÄÖÜäöü]+)", text)
        if not date_match:
            return None
        day = int(date_match.group(1))
        month_name = date_match.group(2)
        month = self._parse_month(month_name)
        if not month:
            return None

        base = self._compose_date(day, month)
        if not base:
            return None

        hour, minute = (int(part) for part in time_str.split(":", 1))
        return base.replace(hour=hour, minute=minute)

    def _parse_month(self, month_name: str) -> int | None:
        if not month_name:
            return None
        key = month_name.strip().lower()
        if key in ENGLISH_MONTH_MAP:
            return ENGLISH_MONTH_MAP[key]
        if key in GERMAN_MONTH_MAP:
            return GERMAN_MONTH_MAP[key]
        return None

    def _compose_date(self, day: int, month: int) -> datetime | None:
        """Compose a Berlin-tz datetime from day/month with a future-aware year."""
        try:
            today = datetime.now(BERLIN_TZ)
            year = today.year
            dt = datetime(year, month, day, 20, 0, tzinfo=BERLIN_TZ)
        except ValueError:
            return None

        # If the date is in the past, roll to next year.
        if dt.date() < (today.date() - timedelta(days=1)):
            try:
                dt = dt.replace(year=year + 1)
            except ValueError:
                return None
        return dt
