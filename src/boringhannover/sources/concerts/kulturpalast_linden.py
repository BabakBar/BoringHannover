"""Kulturpalast Linden Hannover source.

Fetches upcoming events via the venue's iCalendar feed (The Events Calendar).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import ClassVar

from ics import Calendar

from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.sources.base import BaseSource, create_http_client, register_source


__all__ = ["KulturpalastLindenSource"]

logger = logging.getLogger(__name__)


@register_source("kulturpalast_linden")
class KulturpalastLindenSource(BaseSource):
    """Scraper for Kulturpalast Linden (via iCalendar feed).

    Website: https://kulturpalast-hannover.de/events/

    Attributes:
        source_name: "Kulturpalast Linden"
        source_type: "concert"
    """

    source_name: ClassVar[str] = "Kulturpalast Linden"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 60

    ICAL_URL: ClassVar[str] = "https://kulturpalast-hannover.de/events/?ical=1"
    ADDRESS: ClassVar[str] = "Deisterstraße 24, 30449 Hannover"

    def fetch(self) -> list[Event]:
        """Fetch events from the Kulturpalast iCalendar feed."""
        logger.info("Fetching concerts from %s", self.source_name)

        with create_http_client() as client:
            response = client.get(self.ICAL_URL)
            response.raise_for_status()
            events = self._parse_calendar(response.text)

        logger.info("Found %d events from %s", len(events), self.source_name)
        return events

    def _parse_calendar(self, ics_text: str) -> list[Event]:
        events: list[Event] = []
        sanitized = self._sanitize_ics(ics_text)
        try:
            calendar = Calendar(sanitized)
        except Exception as exc:
            logger.warning("Failed to parse iCalendar for %s: %s", self.source_name, exc)
            return events

        for ics_event in sorted(calendar.events, key=lambda e: e.begin):
            event = self._parse_event(ics_event)
            if event:
                events.append(event)
                if self.max_events and len(events) >= self.max_events:
                    break
        return events

    def _parse_event(self, ics_event) -> Event | None:
        try:
            title = str(getattr(ics_event, "name", "") or "").strip()
            if not title:
                return None

            begin = getattr(ics_event, "begin", None)
            if not begin:
                return None
            event_date = begin.datetime
            if event_date.tzinfo is None or event_date.tzinfo.utcoffset(event_date) is None:
                event_date = event_date.replace(tzinfo=BERLIN_TZ)
            else:
                event_date = event_date.astimezone(BERLIN_TZ)

            # If it's an all-day event, default to 20:00 to avoid midnight in UI.
            if getattr(ics_event, "all_day", False) and event_date.time().hour == 0:
                event_date = event_date.replace(hour=20, minute=0)

            url = str(getattr(ics_event, "url", "") or "").strip()
            if not url:
                url = "https://kulturpalast-hannover.de/events/"

            description = str(getattr(ics_event, "description", "") or "")
            subtitle = self._first_description_line(description)

            return Event(
                title=title,
                date=event_date,
                venue=self.source_name,
                url=url,
                category="radar",
                metadata={
                    "time": event_date.strftime("%H:%M"),
                    "description": subtitle or "",
                    "event_type": "event",
                    "address": self.ADDRESS,
                },
            )
        except Exception as exc:
            logger.debug("Error parsing %s event: %s", self.source_name, exc)
            return None

    def _first_description_line(self, description: str) -> str | None:
        if not description:
            return None
        normalized = description.replace("\\n", "\n")
        for line in normalized.splitlines():
            cleaned = " ".join(line.split())
            cleaned = cleaned.rstrip("\\")
            if cleaned:
                return cleaned[:200]
        return None

    def _sanitize_ics(self, ics_text: str) -> str:
        """Fix common ICS issues that break parsing.

        Currently handles events where DTEND is earlier than DTSTART
        on the same date (cross-midnight events).
        """
        lines = ics_text.splitlines()
        output: list[str] = []
        in_event = False
        event_lines: list[str] = []

        for line in lines:
            if line.startswith("BEGIN:VEVENT"):
                in_event = True
                event_lines = [line]
                continue
            if in_event:
                event_lines.append(line)
                if line.startswith("END:VEVENT"):
                    fixed = self._fix_event_block(event_lines)
                    if fixed:
                        output.extend(fixed)
                    in_event = False
                continue
            output.append(line)

        # If file ends mid-event, ignore the partial block.
        return "\n".join(output)

    def _fix_event_block(self, lines: list[str]) -> list[str] | None:
        dtend_idx = None
        dtstart_val = None
        dtend_val = None

        for idx, line in enumerate(lines):
            if line.startswith("DTSTART"):
                dtstart_val = self._parse_ics_datetime(line)
            if line.startswith("DTEND"):
                dtend_idx = idx
                dtend_val = self._parse_ics_datetime(line)

        if dtstart_val and dtend_val and dtend_val < dtstart_val:
            # If it's the same date, assume cross-midnight and bump end by 1 day.
            if dtend_val.date() == dtstart_val.date():
                dtend_val = dtend_val + timedelta(days=1)
                if dtend_idx is not None:
                    lines[dtend_idx] = self._format_ics_datetime(
                        lines[dtend_idx], dtend_val
                    )
            else:
                # Drop invalid event to avoid breaking the calendar parse.
                return None

        return lines

    def _parse_ics_datetime(self, line: str) -> datetime | None:
        """Parse an ICS datetime line into a naive datetime."""
        if ":" not in line:
            return None
        value = line.split(":", 1)[1].strip()
        # DATE-only
        if len(value) == 8 and value.isdigit():
            try:
                return datetime(
                    int(value[0:4]),
                    int(value[4:6]),
                    int(value[6:8]),
                    0,
                    0,
                    tzinfo=BERLIN_TZ,
                )
            except ValueError:
                return None

        if "T" in value:
            date_part, time_part = value.split("T", 1)
            time_part = time_part.rstrip("Z")
            time_part = time_part[:6]
            try:
                dt_date = date(
                    int(date_part[0:4]),
                    int(date_part[4:6]),
                    int(date_part[6:8]),
                )
            except ValueError:
                return None
            try:
                hour = int(time_part[0:2])
                minute = int(time_part[2:4])
            except ValueError:
                return None
            second = int(time_part[4:6]) if len(time_part) >= 6 else 0
            return datetime(
                dt_date.year,
                dt_date.month,
                dt_date.day,
                hour,
                minute,
                second,
                tzinfo=BERLIN_TZ,
            )
        return None

    def _format_ics_datetime(self, line: str, value: datetime) -> str:
        """Replace the datetime value in an ICS DTSTART/DTEND line."""
        prefix, _ = line.split(":", 1)
        if ";VALUE=DATE" in prefix:
            return f"{prefix}:{value.strftime('%Y%m%d')}"
        return f"{prefix}:{value.strftime('%Y%m%dT%H%M%S')}"
