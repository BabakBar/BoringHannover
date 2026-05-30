"""Apollokino Hannover-Linden source.

Scrapes the OmU-Nachtstudio page for original-version showings and enriches
each entry inside the lookahead window with detail-page metadata
(year, country, duration, rating, director, cast, trailer).
"""

from __future__ import annotations

import contextlib
import logging
import re
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from boringhannover.config import SCRAPE_DELAY_SECONDS
from boringhannover.constants import BERLIN_TZ, EVENT_LOOKAHEAD_DAYS
from boringhannover.models import Event
from boringhannover.sources.base import (
    BaseSource,
    create_http_client,
    parse_german_date,
    register_source,
)


if TYPE_CHECKING:
    import httpx


__all__ = ["ApollokinoSource"]

logger = logging.getLogger(__name__)


@register_source("apollokino")
class ApollokinoSource(BaseSource):
    """Apollokino Hannover-Linden — OmU-Nachtstudio (original-version) shows."""

    source_name: ClassVar[str] = "Apollokino Hannover"
    source_type: ClassVar[str] = "cinema"

    PAGE_URL: ClassVar[str] = "https://www.apollokino.de/?mp=OmU-Nachtstudio"

    TIME_TITLE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<time>\d{1,2}:\d{2}):?\s*(?P<title>.+)$"
    )

    BLACKLIST: ClassVar[tuple[str, ...]] = ("desimo", "spezial club")

    # Short country codes — exact match only. Substring matching against
    # these would mis-tag long names (e.g. "Australien" contains "at").
    _LANGUAGE_BY_CODE: ClassVar[dict[str, str]] = {
        "usa": "Englisch",
        "us": "Englisch",
        "gb": "Englisch",
        "uk": "Englisch",
        "ie": "Englisch",
        "dk": "Dänisch",
        "fr": "Französisch",
        "de": "Deutsch",
        "it": "Italienisch",
        "es": "Spanisch",
        "jp": "Japanisch",
        "se": "Schwedisch",
        "no": "Norwegisch",
        "pl": "Polnisch",
        "pt": "Portugiesisch",
        "nl": "Niederländisch",
        "be": "Niederländisch",
        "ch": "Deutsch",
        "at": "Deutsch",
        "gr": "Griechisch",
        "tr": "Türkisch",
    }

    # Full German country names — safe to substring-match (long enough).
    _LANGUAGE_BY_NAME: ClassVar[dict[str, str]] = {
        "deutschland": "Deutsch",
        "österreich": "Deutsch",
        "schweiz": "Deutsch",
        "england": "Englisch",
        "großbritannien": "Englisch",
        "irland": "Englisch",
        "usa": "Englisch",
        "kanada": "Englisch",
        "australien": "Englisch",
        "neuseeland": "Englisch",
        "frankreich": "Französisch",
        "italien": "Italienisch",
        "spanien": "Spanisch",
        "japan": "Japanisch",
        "schweden": "Schwedisch",
        "norwegen": "Norwegisch",
        "dänemark": "Dänisch",
        "polen": "Polnisch",
        "portugal": "Portugiesisch",
        "niederlande": "Niederländisch",
        "belgien": "Niederländisch",
        "griechenland": "Griechisch",
        "türkei": "Türkisch",
        "russland": "Russisch",
        "korea": "Koreanisch",
        "china": "Chinesisch",
        "indien": "Hindi",
        "brasilien": "Portugiesisch",
        "mexiko": "Spanisch",
        "argentinien": "Spanisch",
    }

    def fetch(self) -> list[Event]:
        logger.info("Fetching Apollokino page: %s", self.PAGE_URL)

        events: list[Event] = []
        now = datetime.now(BERLIN_TZ)
        cutoff = now + timedelta(days=EVENT_LOOKAHEAD_DAYS)

        with create_http_client() as client:
            resp = client.get(self.PAGE_URL)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for date_line in soup.find_all("div", class_="datumzeile"):
                if not isinstance(date_line, Tag):
                    continue

                base_date = parse_german_date(
                    date_line.get_text(separator=" ", strip=True)
                )
                if base_date is None:
                    continue

                film_table = self._find_film_table(date_line)
                if film_table is None:
                    continue

                for row in self._iter_show_rows(film_table):
                    event = self._parse_row(row, base_date, client, now, cutoff)
                    if event is not None:
                        events.append(event)

        logger.info("Apollokino: parsed %d events", len(events))
        return events

    @staticmethod
    def _find_film_table(date_line: Tag) -> Tag | None:
        nxt = date_line.next_sibling
        while nxt is not None:
            if (
                isinstance(nxt, Tag)
                and nxt.name == "table"
                and "filmtabelle" in (nxt.get("class") or [])
            ):
                return nxt
            nxt = nxt.next_sibling

        fallback = date_line.find_next("table", class_="filmtabelle")
        return fallback if isinstance(fallback, Tag) else None

    @staticmethod
    def _iter_show_rows(film_table: Tag) -> list[Tag]:
        return [
            tr
            for tagestabelle in film_table.find_all("table", class_="tagestabelle")
            if isinstance(tagestabelle, Tag)
            for tr in tagestabelle.find_all("tr")
            if isinstance(tr, Tag)
        ]

    def _parse_row(
        self,
        row: Tag,
        base_date: datetime,
        client: httpx.Client,
        now: datetime,
        cutoff: datetime,
    ) -> Event | None:
        td = row.find("td")
        if not isinstance(td, Tag):
            return None

        title_text, detail_href = self._extract_title_and_link(td)
        match = self.TIME_TITLE_RE.match(title_text)
        if not match:
            return None

        time_str = match.group("time")
        title = match.group("title").strip()

        try:
            hour, minute = (int(part) for part in time_str.split(":"))
            dt = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError:
            return None

        note = self._text_of(td.find("div", class_="filmanmerkung"))
        note_lower = note.lower()
        title_lower = title.lower()

        # The OmU page sometimes injects unrelated events; require the marker
        # and reject the recurring non-film hosts (Desimo, Spezial Club).
        is_omu = "omu-nachtstudio" in note_lower
        is_blacklisted = any(
            term in note_lower or term in title_lower for term in self.BLACKLIST
        )
        if not is_omu or is_blacklisted:
            logger.debug(
                "Skipping row %r (omu=%s blacklisted=%s)", title, is_omu, is_blacklisted
            )
            return None

        metadata: dict[str, Any] = {
            "synopsis": self._text_of(td.find("div", class_="filminhalt")),
            "original_version": True,
            "poster_url": self._absolute_url(self._attr(td.find("img"), "src")),
        }

        detail_url = self._absolute_url(detail_href)
        if detail_url and now <= dt <= cutoff:
            detail_meta = self._fetch_detail_metadata(detail_url, client=client)
            if detail_meta:
                metadata.update(detail_meta)
                time.sleep(SCRAPE_DELAY_SECONDS)

        ticket_url = self._absolute_url(self._attr(td.find("form"), "action"))

        try:
            return Event(
                title=title,
                date=dt,
                venue=self.source_name,
                url=detail_url or ticket_url or self.PAGE_URL,
                category="movie",
                metadata=metadata,
            )
        except (ValueError, TypeError) as exc:
            logger.warning("Skipping invalid Apollokino event %r: %s", title, exc)
            return None

    def _fetch_detail_metadata(
        self, url: str, *, client: httpx.Client | None = None
    ) -> dict[str, Any]:
        """Fetch a detail page; return ``{}`` on any failure."""
        try:
            if client is None:
                with create_http_client() as own_client:
                    resp = own_client.get(url)
                    resp.raise_for_status()
                    html = resp.text
            else:
                resp = client.get(url)
                resp.raise_for_status()
                html = resp.text
        except Exception as exc:
            logger.warning("Apollokino detail fetch failed for %s: %s", url, exc)
            return {}

        return self._extract_metadata(BeautifulSoup(html, "html.parser"))

    def _extract_metadata(self, soup: BeautifulSoup) -> dict[str, Any]:
        out: dict[str, Any] = {}

        filmdaten = self._text_of(soup.find("div", class_="filmdaten"))
        parsed = self._parse_filmdaten(filmdaten)

        for key in ("duration", "rating", "year"):
            if parsed.get(key) is not None:
                out[key] = parsed[key]
        if parsed.get("country"):
            out["country"] = parsed["country"]
        out["language"] = self._derive_language_from_country(parsed.get("country", ""))
        if parsed.get("cast"):
            out["cast"] = parsed["cast"]

        homepage = soup.find("div", class_="filmhomepage")
        if isinstance(homepage, Tag):
            href = self._attr(homepage.find("a"), "href")
            if href:
                out["trailer_url"] = href

        synopsis = self._text_of(soup.find("div", class_="filminhalt"))
        if synopsis:
            out["synopsis"] = synopsis

        return out

    def _parse_filmdaten(self, text: str) -> dict[str, Any]:
        """Pull structured fields out of the freeform ``div.filmdaten`` text.

        Example: ``USA 1975, 124 Min., ab 16 J., R: Steven Spielberg,
        mit: Roy Scheider, Robert Shaw, ... u.a.``
        """
        out: dict[str, Any] = {
            "country": "",
            "year": None,
            "duration": None,
            "rating": None,
            "cast": [],
        }
        if not text:
            return out

        year_m = re.search(r"\b(19|20)\d{2}\b", text)
        if year_m:
            with contextlib.suppress(ValueError):
                out["year"] = int(year_m.group(0))

        country_m = re.match(
            r"\s*([A-Za-zÄÖÜäöüß0-9\-/ ]+?)\s*(?:,|\b(?:19|20)\d{2}\b)",
            text,
        )
        if country_m:
            out["country"] = country_m.group(1).strip()

        dur_m = re.search(r"(\d{2,3})\s*Min\.?", text)
        if dur_m:
            with contextlib.suppress(ValueError):
                out["duration"] = int(dur_m.group(1))

        rating_m = re.search(
            r"(?:FSK[:\s]*|ab\s+)(\d{1,2})(?:\s*J\.?)?",
            text,
            re.IGNORECASE,
        )
        if rating_m:
            with contextlib.suppress(ValueError):
                out["rating"] = int(rating_m.group(1))

        cast = self._parse_cast(text)
        if cast:
            out["cast"] = cast

        return out

    def _parse_cast(self, text: str) -> list[dict[str, str]]:
        """Extract ``R:`` (director) and ``mit:`` (cast) as Astor-shaped dicts."""
        people: list[dict[str, str]] = []

        director_m = re.search(
            r"R:\s*(.+?)(?=\s*,\s*(?:mit:|Länge:|FSK[:\s])|\s*$)",
            text,
            re.IGNORECASE,
        )
        if director_m:
            people.extend(
                {"role": "Regie", "name": name}
                for name in self._split_names(director_m.group(1))
            )

        cast_m = re.search(
            r"mit:\s*(.+?)(?=\s*(?:Länge:|FSK[:\s]|R:)|\s*$)",
            text,
            re.IGNORECASE,
        )
        if cast_m:
            people.extend(
                {"role": "Darsteller", "name": name}
                for name in self._split_names(cast_m.group(1))
            )

        return people

    @classmethod
    def _split_names(cls, raw: str) -> list[str]:
        parts = [p.strip() for p in re.split(r",\s*|\s+und\s+", raw) if p.strip()]
        names: list[str] = []
        for part in parts:
            cleaned = cls._clean_cast_name(part)
            if not cleaned or cleaned.lower().startswith(("länge", "fsk")):
                continue
            names.append(cleaned)
        return names

    @staticmethod
    def _clean_cast_name(name: str) -> str:
        name = re.sub(r"\(.*?\)", "", name)
        name = re.sub(r"\bu\.?\s*a\.?\b", "", name)
        # Trim stray punctuation incl. the leading ':' the site sometimes emits
        # for "mit: : Name, ..." style filmdaten.
        return name.strip(" \t:,.;")

    @classmethod
    def _derive_language_from_country(cls, country: str) -> str:
        """Format the language string the way exporters expect.

        Apollokino OmU shows always have German subtitles. We only add the
        spoken-language token when the country uniquely identifies one.
        """
        if not country or "," in country or "/" in country:
            return "Untertitel: Deutsch"

        c = country.strip().lower()
        lang = cls._LANGUAGE_BY_CODE.get(c) or cls._LANGUAGE_BY_NAME.get(c)
        if lang is None:
            # Substring match only against full names — codes are too short
            # to substring-match safely (e.g. "at" inside "australien").
            for name, language in cls._LANGUAGE_BY_NAME.items():
                if name in c:
                    lang = language
                    break

        if lang:
            return f"Sprache: {lang}, Untertitel: Deutsch"
        return "Untertitel: Deutsch"

    @staticmethod
    def _text_of(node: Any) -> str:
        if isinstance(node, Tag):
            return node.get_text(separator=" ", strip=True)
        return ""

    @staticmethod
    def _attr(node: Any, name: str) -> str:
        if isinstance(node, Tag):
            value = node.get(name)
            if isinstance(value, str):
                return value
        return ""

    @classmethod
    def _absolute_url(cls, href: str) -> str:
        return urljoin(cls.PAGE_URL, href) if href else ""

    @classmethod
    def _extract_title_and_link(cls, td: Tag) -> tuple[str, str]:
        anchor = td.find("a")
        if isinstance(anchor, Tag):
            h2 = anchor.find("h2", class_="filmtitel")
            title_text = cls._text_of(h2) or cls._text_of(anchor)
            return title_text, cls._attr(anchor, "href")
        return cls._text_of(td.find("h2", class_="filmtitel")), ""
