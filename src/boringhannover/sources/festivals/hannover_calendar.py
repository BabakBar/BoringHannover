"""Discovery-only source for official Hannover festival listings."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from boringhannover.constants import BERLIN_TZ, EVENT_LOOKAHEAD_DAYS
from boringhannover.date_parsing import log_unknown_month, lookup_german_month
from boringhannover.models import Event
from boringhannover.occasions import (
    Admission,
    OccasionDefinition,
    Occurrence,
    Place,
    ScheduleConfidence,
    SourceStatus,
)
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

# One Termine line: "DD.MM.YYYY [bis DD.MM.YYYY] [ab HH:MM [bis HH:MM] Uhr]".
# Anything after it, such as a weekday ("sonntags"), is not parsed further.
_APPOINTMENT_PATTERN = re.compile(
    r"(?P<start>\d{1,2}\.\d{1,2}\.\d{4})(?:\s+bis\s+(?P<end>\d{1,2}\.\d{1,2}\.\d{4}))?"
    r"(?:\s+ab\s+(?P<from>\d{1,2}:\d{2})(?:\s+bis\s+(?P<to>\d{1,2}:\d{2}))?\s+Uhr)?"
)
_TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})")
_EXCLUSION_LABEL = "Die Veranstaltung findet nicht statt am:"
_MAX_SCHEDULE_DAYS = 366
# hannover.de prefixes a changed entry's title with its status.
_STATUS_PREFIX = re.compile(
    r"(?P<marker>abgesagt|verschoben)\s*:\s*(?P<name>\S.*)", re.I
)
_LOOSE_DATE = (
    r"(?P<{p}day>\d{{1,2}})\.\s*"
    r"(?:(?P<{p}month>\d{{1,2}})\.|(?P<{p}month_name>[a-zäöü]+))"
    r"\s*(?P<{p}year>\d{{4}})?"
)
# The last two Ort lines of a postal address: "Straße 1A" and "30169 Hannover".
_POSTAL_LINE = re.compile(r"(?P<postal_code>\d{5})\s+(?P<locality>\S.*)")
# One entry price, "3 €", "3,50 €" or "€ 3"; anything qualified is unreadable.
_PRICE = re.compile(
    r"(?:(?P<euros>\d+)(?:[.,](?P<cents>\d{1,2}))?\s*€"
    r"|€\s*(?P<euros_after>\d+)(?:[.,](?P<cents_after>\d{1,2}))?)"
)
_FREE_PRICES = frozenset({"frei", "kostenlos", "eintritt frei"})
_FREE_ENTRY_STATEMENT = "Dies ist eine Veranstaltung mit freiem Eintritt"
# An explicit dated move: "vom 30. Juni auf den 12. Juli 2026 verschoben".
_RESCHEDULE_PATTERN = re.compile(
    rf"\bvom\s+{_LOOSE_DATE.format(p='old_')}\s+auf\s+(?:den\s+)?"
    rf"{_LOOSE_DATE.format(p='new_')}",
    re.I,
)


@dataclass(frozen=True, slots=True)
class _DetailSchedule:
    """Dates read from an official Termine row.

    A discrete schedule without occurrences means the source excludes every
    listed date; it is never discoverable.
    """

    start_date: date
    end_date: date
    occurrences: tuple[Occurrence, ...]
    confidence: ScheduleConfidence
    hours_text: str


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
    # Identify ourselves to the city's calendar with a contact; other sources
    # keep the shared browser User-Agent.
    USER_AGENT: ClassVar[str] = (
        "BoringHannover (+https://boringhannover.de/impressum/; "
        "https://github.com/BabakBar/BoringHannover)"
    )

    def fetch(self) -> list[Event]:
        """Return no timeline events; this source discovers parent occasions."""
        return []

    def discover_occasions(self) -> list[OccasionDefinition]:
        """Fetch and normalize the current official festival index."""
        with create_http_client(user_agent=self.USER_AGENT) as client:
            html = self._fetch_calendar_html(client, self.CALENDAR_URL)
            occasions = [
                self._enrich_from_detail(client, occasion)
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
            marker, title = self._split_status(
                self._text(card.select_one(".interesting-single__title"))
            )
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

            start_date, end_date = dates
            source_status, previous_start_date = self._source_status(
                marker, description, start_date
            )
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
                    description="",
                    source_summary=description,
                    source_status=source_status,
                    previous_start_date=previous_start_date,
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
        """Read official detail rows for occasions inside the discovery horizon."""
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
        """Apply official Termine dates, status and a missing location.

        A valid Termine row replaces the listing dates; a corrupt one keeps
        them without inventing appointments.
        """
        schedule = cls._parse_detail_schedule(html)
        if schedule is not None:
            occasion = replace(
                occasion,
                start_date=schedule.start_date,
                end_date=schedule.end_date,
                occurrences=schedule.occurrences,
                schedule_confidence=schedule.confidence,
                hours_text=schedule.hours_text,
            )

        soup = BeautifulSoup(html, "html.parser")
        marker = {
            "cancelled": "abgesagt",
            "postponed": "verschoben",
            "rescheduled": "verschoben",
        }.get(occasion.source_status or "")
        if marker is None:
            marker, _ = cls._split_status(
                cls._text(soup.select_one("h1.content-detail__title"))
            )
        summary = cls._text(soup.select_one(".content-detail__summary"))
        source_status, previous_start_date = cls._source_status(
            marker, f"{occasion.source_summary} {summary}", occasion.start_date
        )
        return replace(
            occasion,
            location=occasion.location or cls._parse_detail_location(html),
            source_status=source_status or occasion.source_status,
            previous_start_date=previous_start_date,
            place=cls._parse_detail_place(html) or occasion.place,
            admission=cls._parse_detail_admission(html) or occasion.admission,
        )

    @classmethod
    def _parse_detail_schedule(cls, html: str) -> _DetailSchedule | None:
        """Read appointments and exclusions from the official Termine row.

        An exact line (a date or range with optional hours) confirms every
        listed day; excluded days are removed first, so they never become an
        end. A line with trailing wording such as "sonntags" only bounds a
        source window: none of its days is confirmed, its stated ends are kept
        rather than guessed, and the source wording becomes hours text. A row
        whose dates are all excluded is a known schedule without appointments.
        Invalid, reversed or contradictory dates reject the whole row.
        """
        cell = cls._detail_cell(html, "termine")
        if cell is None:
            return None

        positive: list[str] = []
        excluded: list[str] = []
        lines = positive
        for line in cls._cell_lines(cell):
            head, *tail = re.split(
                re.escape(_EXCLUSION_LABEL), line, maxsplit=1, flags=re.I
            )
            lines.append(head)
            if tail:
                lines = excluded
                lines.append(tail[0])

        excluded_dates: set[date] = set()
        for match in _DATE_PATTERN.finditer(" ".join(excluded)):
            excluded_day = cls._date(match.group(0))
            if excluded_day is None:
                return None
            excluded_dates.add(excluded_day)

        hours_lines = [line.strip() for line in positive if line.strip()]
        confirmed: dict[date, tuple[str | None, str | None]] = {}
        listed: list[date] = []
        bounds: list[date] = []
        exact = True
        for line in hours_lines:
            match = _APPOINTMENT_PATTERN.match(line)
            if match is None:
                # Dates after an unknown label ("...am:") may be exclusions.
                if _DATE_PATTERN.search(line) or line.endswith(":"):
                    return None
                exact = False
                continue
            if _DATE_PATTERN.search(line, match.end()):
                return None

            start = cls._date(match["start"])
            end = cls._date(match["end"]) if match["end"] else start
            start_time = cls._time(match["from"]) if match["from"] else None
            end_time = cls._time(match["to"], end=True) if match["to"] else None
            if (
                start is None
                or end is None
                or not 0 <= (end - start).days <= _MAX_SCHEDULE_DAYS
                or (match["from"] and start_time is None)
                or (match["to"] and end_time is None)
            ):
                return None
            if start_time is None or (end_time is not None and end_time <= start_time):
                end_time = None

            listed += [start, end]
            days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
            remaining = [day for day in days if day not in excluded_dates]
            if not remaining:
                continue
            if match.end() != len(line):
                exact = False
                bounds += [start, end]
                continue
            bounds += remaining
            for day in remaining:
                if confirmed.setdefault(day, (start_time, end_time)) != (
                    start_time,
                    end_time,
                ):
                    exact = False

        if not listed:
            return None
        if not bounds:
            return _DetailSchedule(min(listed), max(listed), (), "discrete", "")
        start_date, end_date = min(bounds), max(bounds)

        if not exact:
            hours_text = "; ".join(hours_lines)
            if excluded_dates:
                skipped = ", ".join(
                    day.strftime("%d.%m.%Y") for day in sorted(excluded_dates)
                )
                hours_text = f"{hours_text}. {_EXCLUSION_LABEL} {skipped}"
            return _DetailSchedule(start_date, end_date, (), "unknown", hours_text)

        span = (end_date - start_date).days + 1
        return _DetailSchedule(
            start_date=start_date,
            end_date=end_date,
            occurrences=tuple(
                Occurrence(day, *confirmed[day]) for day in sorted(confirmed)
            ),
            confidence="continuous" if len(confirmed) == span else "discrete",
            hours_text="",
        )

    @staticmethod
    def _cell_lines(cell: Tag) -> list[str]:
        """Return a detail cell's block children as whitespace-normalized lines."""
        for line_break in cell.find_all("br"):
            line_break.replace_with(" ")
        lines: list[str] = []
        for child in cell.children:
            if isinstance(child, Tag):
                text = child.get_text(" ")
            elif isinstance(child, NavigableString) and not isinstance(child, Comment):
                text = str(child)
            else:
                continue
            if normalized := " ".join(text.split()):
                lines.append(normalized)
        return lines

    @staticmethod
    def _date(value: str) -> date | None:
        """Parse one DD.MM.YYYY date; None if it does not exist."""
        day, month, year = value.split(".")
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None

    @staticmethod
    def _time(value: str, *, end: bool = False) -> str | None:
        """Normalize a confirmed HH:MM time; 24:00 is valid only as an end."""
        match = _TIME_PATTERN.fullmatch(value)
        if match is None:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        if minute > 59 or hour > 24 or (hour == 24 and (minute or not end)):
            return None
        return f"{hour:02d}:{minute:02d}"

    @staticmethod
    def _split_status(title: str) -> tuple[str | None, str]:
        """Split an official "Abgesagt:"/"Verschoben:" prefix from a title."""
        match = _STATUS_PREFIX.fullmatch(title.strip())
        if match is None:
            return None, title
        return match["marker"].casefold(), match["name"].strip()

    @classmethod
    def _source_status(
        cls,
        marker: str | None,
        text: str,
        start_date: date,
    ) -> tuple[SourceStatus | None, date | None]:
        """Return explicit source status and a verified rescheduling's old date.

        A postponement counts as rescheduled only when the text names a new
        date equal to the listed start and an original date with its own
        year, in either direction. An original year is never inferred.
        """
        if marker == "abgesagt":
            return "cancelled", None
        if marker != "verschoben":
            return None, None
        for match in _RESCHEDULE_PATTERN.finditer(text):
            if match["old_year"] is None:
                continue
            if cls._loose_date(match, "new_", start_date.year) != start_date:
                continue
            old = cls._loose_date(match, "old_", start_date.year)
            if old is not None and old != start_date:
                return "rescheduled", old
        return "postponed", None

    @classmethod
    def _loose_date(
        cls,
        match: re.Match[str],
        prefix: str,
        year: int,
    ) -> date | None:
        """Read a German numeric or month-name date from a reschedule match.

        ``year`` applies only when the date states none; the listed start
        supplies it for the new date, which must then equal that start.
        """
        month_name = match[f"{prefix}month_name"]
        month = (
            lookup_german_month(month_name)
            if month_name
            else int(match[f"{prefix}month"])
        )
        if month is None:
            log_unknown_month(
                month_name,
                source_key="hannover_festival_calendar",
                raw_value=match.group(0),
                field="previous_start" if prefix == "old_" else "rescheduled_start",
            )
            return None
        try:
            return date(
                int(match[f"{prefix}year"] or year), month, int(match[f"{prefix}day"])
            )
        except ValueError:
            return None

    @classmethod
    def _parse_detail_location(cls, html: str) -> str:
        """Return the official detail-page Ort row as one address line."""
        return ", ".join(cls._ort_lines(html))

    @classmethod
    def _parse_detail_place(cls, html: str) -> Place | None:
        """Return the Ort row as a postal address, or None if it is not one.

        The row reads [venue,] street with a house number, "PLZ locality".
        A venue name alone is not an address, so it gets no directions.
        """
        lines = cls._ort_lines(html)
        if len(lines) < 2:
            return None
        postal = _POSTAL_LINE.fullmatch(lines[-1])
        street = lines[-2]
        if postal is None or not any(character.isdigit() for character in street):
            return None
        return Place(
            street=street,
            postal_code=postal["postal_code"],
            locality=postal["locality"],
            venue=" ".join(lines[:-2]),
        )

    @classmethod
    def _parse_detail_admission(cls, html: str) -> tuple[Admission, ...]:
        """Read official entry prices in source order.

        Prices are a nested table under the Termine and Ort rows; a free
        event says so in one sentence instead. One unreadable row makes the
        whole entry unknown, so a condition is never dropped from a price.
        """
        soup = BeautifulSoup(html, "html.parser")
        admission: list[Admission] = []
        for row in soup.select(".details-table .table.details-table .detail-row"):
            cells = row.select(".detail-cell")
            label = cls._text(cells[0]) if len(cells) == 2 else ""
            price = cls._price(cls._text(cells[1])) if label else None
            if price is None:
                return ()
            admission.append(Admission(price=price, label=label))
        if admission:
            return tuple(admission)
        if any(
            cls._text(statement).rstrip(".") == _FREE_ENTRY_STATEMENT
            for statement in soup.select(".details-table > p")
        ):
            return (Admission(price="free"),)
        return ()

    @staticmethod
    def _price(value: str) -> str | None:
        """Normalize one listed price to "free" or English "€3.50" notation."""
        if value.casefold() in _FREE_PRICES:
            return "free"
        match = _PRICE.fullmatch(value)
        if match is None:
            return None
        euros = int(match["euros"] or match["euros_after"])
        cents = match["cents"] or match["cents_after"]
        return f"€{euros}.{cents.ljust(2, '0')}" if cents else f"€{euros}"

    @classmethod
    def _ort_lines(cls, html: str) -> list[str]:
        """Return the official Ort row's lines, whitespace-normalized."""
        cell = cls._detail_cell(html, "ort")
        if cell is None:
            return []
        for line_break in cell.find_all("br"):
            line_break.replace_with("\n")
        lines = (" ".join(line.split()) for line in cell.get_text(" ").split("\n"))
        return [line for line in lines if line]

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

        if parsed[-1] < parsed[0]:
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
            f"{occasion.name} {occasion.location} {occasion.source_summary}"
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
