"""Hannover 96 home-match source using the club's official calendar feed."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import ClassVar

from ics import Calendar

from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import CONFIRMED_TIME
from boringhannover.models import Event
from boringhannover.sources.base import BaseSource, create_http_client, register_source


__all__ = ["Hannover96Source"]

logger = logging.getLogger(__name__)


@register_source("hannover_96")
class Hannover96Source(BaseSource):
    """Fetch confirmed public home matches from Hannover 96's calendar."""

    source_name: ClassVar[str] = "Hannover 96"
    source_type: ClassVar[str] = "sport"
    max_events: ClassVar[int | None] = 60

    ICAL_URL: ClassVar[str] = (
        "https://www.hannover96.de/fileadmin/appointments/match.ics"
    )
    SCHEDULE_URL: ClassVar[str] = (
        "https://www.hannover96.de/matchcenter/profis/profis-spielplan"
    )
    ARENA_ADDRESS: ClassVar[str] = "Robert-Enke-Straße 3, 30169 Hannover"

    _ABBREVIATIONS: ClassVar[dict[str, str]] = {
        "BOC": "VfL Bochum",
        "BSC": "Hertha BSC",
        "DSC": "Arminia Bielefeld",
        "EBS": "Eintracht Braunschweig",
        "ELV": "SV Elversberg",
        "F95": "Fortuna Düsseldorf",
        "FCE": "Energie Cottbus",
        "FCK": "1. FC Kaiserslautern",
        "FCM": "1. FC Magdeburg",
        "FCN": "1. FC Nürnberg",
        "KIE": "Holstein Kiel",
        "KSC": "Karlsruher SC",
        "OSN": "VfL Osnabrück",
        "PRM": "Preußen Münster",
        "S04": "FC Schalke 04",
        "SCP": "SC Paderborn 07",
        "SGD": "Dynamo Dresden",
        "SGF": "SpVgg Greuther Fürth",
        "SVD": "SV Darmstadt 98",
        "WOB": "VfL Wolfsburg",
    }

    _ABBREVIATED_HOME_MATCH: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<competition>.+?)\s+-\s+H96\s+vs\.\s+(?P<opponent>.+)$"
    )
    _NAMED_HOME_MATCH: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<competition>[^:]+):\s+Hannover 96\s+-\s+(?P<opponent>.+)$"
    )

    def fetch(self) -> list[Event]:
        """Fetch Hannover 96's official calendar and return home matches."""
        logger.info("Fetching home matches from %s", self.source_name)

        with create_http_client() as client:
            response = client.get(self.ICAL_URL)
            response.raise_for_status()
            events = self._parse_calendar(response.text)

        logger.info("Found %d home matches from %s", len(events), self.source_name)
        return events

    def _parse_calendar(
        self,
        ics_text: str,
        *,
        now: datetime | None = None,
    ) -> list[Event]:
        reference_time = now or datetime.now(BERLIN_TZ)
        if (
            reference_time.tzinfo is None
            or reference_time.tzinfo.utcoffset(reference_time) is None
        ):
            reference_time = reference_time.replace(tzinfo=BERLIN_TZ)
        else:
            reference_time = reference_time.astimezone(BERLIN_TZ)

        try:
            calendar = Calendar(ics_text)
        except Exception as exc:
            logger.warning(
                "Failed to parse iCalendar for %s: %s", self.source_name, exc
            )
            return []

        events: list[Event] = []
        for ics_event in sorted(calendar.events, key=lambda event: event.begin):
            event = self._parse_event(ics_event, reference_time)
            if event is None:
                continue
            events.append(event)
            if self.max_events and len(events) >= self.max_events:
                break
        return events

    def _parse_event(self, ics_event, now: datetime) -> Event | None:
        title = str(getattr(ics_event, "name", "") or "").strip()
        description = str(getattr(ics_event, "description", "") or "").strip()
        if "nicht öffentlich" in f"{title}\n{description}".casefold():
            return None

        match = self._match_home_title(title)
        if match is None or getattr(ics_event, "all_day", False):
            return None

        begin = getattr(ics_event, "begin", None)
        if begin is None:
            return None
        event_date = begin.datetime
        if event_date.tzinfo is None or event_date.tzinfo.utcoffset(event_date) is None:
            event_date = event_date.replace(tzinfo=BERLIN_TZ)
        else:
            event_date = event_date.astimezone(BERLIN_TZ)
        if event_date < now:
            return None

        competition, raw_opponent = match
        opponent = self._expand_opponent(raw_opponent)
        venue = self._extract_venue(ics_event, description)
        metadata = {
            "time": event_date.strftime("%H:%M"),
            "time_confidence": CONFIRMED_TIME,
            "event_type": "sport",
            "competition": competition,
            "opponent": opponent,
        }
        if venue.casefold() == "heinz von heiden arena":
            metadata["address"] = self.ARENA_ADDRESS

        return Event(
            title=f"Hannover 96 vs. {opponent}",
            date=event_date,
            venue=venue,
            url=self.SCHEDULE_URL,
            category="radar",
            metadata=metadata,
        )

    def _match_home_title(self, title: str) -> tuple[str, str] | None:
        for pattern in (self._ABBREVIATED_HOME_MATCH, self._NAMED_HOME_MATCH):
            match = pattern.fullmatch(title)
            if match:
                return (
                    match.group("competition").strip(),
                    match.group("opponent").strip(),
                )
        return None

    def _expand_opponent(self, opponent: str) -> str:
        return self._ABBREVIATIONS.get(opponent, opponent)

    def _extract_venue(self, ics_event, description: str) -> str:
        location = str(getattr(ics_event, "location", "") or "").strip()
        if location:
            return location

        venue_match = re.search(r"(?:^|\n)Ort:\s*([^\\\n]+)", description)
        if venue_match:
            return venue_match.group(1).strip()
        return self.source_name
