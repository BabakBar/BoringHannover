"""Scraper for Apollokino Hannover-Linden.

Parses Apollokino HTML pages. The pages use repeated sections 
with a `div.datumzeile` followed by `table.filmtabelle`. 
Each film entry is represented inside a `table.tagestabelle`.

Apollokino has a separate page for OV shows (OmU-Nachtstudio)
that we focus on for now:
https://www.apollokino.de/?mp=OmU-Nachtstudio

Main page for the weekly schedule, including dubbed versions:
https://www.apollokino.de/?v=&mp=Diese%20Woche
"""

from __future__ import annotations

import logging
import time
import re
from datetime import datetime, timedelta
from typing import ClassVar, Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from boringhannover.models import Event
from boringhannover.sources.base import (
    BaseSource,
    create_http_client,
    parse_german_date,
    is_original_version,
    register_source,
)
from boringhannover.constants import MOVIES_LOOKAHEAD_DAYS, BERLIN_TZ
from boringhannover.config import SCRAPE_DELAY_SECONDS


__all__ = ["ApollokinoSource"]

logger = logging.getLogger(__name__)


@register_source("apollokino")
class ApollokinoSource(BaseSource):
    """Scraper for the Apollokino Hannover-Linden."""

    source_name: ClassVar[str] = "Apollokino Hannover"
    source_type: ClassVar[str] = "cinema"

    # Use the OmU-specific page
    PAGE_URL: ClassVar[str] = "https://www.apollokino.de/?mp=OmU-Nachtstudio"

    TIME_TITLE_RE = re.compile(r"^(?P<time>\d{1,2}:\d{2}):?\s*(?P<title>.+)$")
    # Exclude known non-film shows
    BLACKLIST = ("desimo", "spezial club")

    def fetch(self) -> list[Event]:
        logger.info("Fetching Apollokino page: %s", self.PAGE_URL)
        with create_http_client() as client:
            resp = client.get(self.PAGE_URL)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

        events: list[Event] = []

        now = datetime.now(BERLIN_TZ)
        cutoff = now + timedelta(days=MOVIES_LOOKAHEAD_DAYS)

        # Iterate over date blocks: a date line followed by a filmtabelle
        date_lines = soup.find_all("div", class_="datumzeile")
        for date_line in date_lines:
            date_text = date_line.get_text(separator=" ", strip=True)
            base_date = parse_german_date(date_text)
            if base_date is None:
                logger.debug("Could not parse date from: %s", date_text)
                continue

            # Next sibling(s) may include whitespace/text nodes; find next table.filmtabelle
            table = None
            nxt = date_line.next_sibling
            while nxt is not None:
                # BeautifulSoup may return strings; ensure Tag
                if getattr(nxt, "name", None) == "table" and "filmtabelle" in (nxt.get("class") or []):
                    table = nxt
                    break
                nxt = nxt.next_sibling

            if table is None:
                # Try a fallback: searchNearby
                table = date_line.find_next("table", class_="filmtabelle")
            if table is None:
                continue

            # Inside filmtabelle -> find inner tagestabelle and film rows
            for tagestabelle in table.find_all("table", class_="tagestabelle"):
                for tr in tagestabelle.find_all("tr"):
                    td = tr.find("td")
                    if not td:
                        continue

                    # Title & time
                    a = td.find("a")
                    title_text = ""
                    detail_href = ""
                    if a:
                        title_el = a.find("h2", class_="filmtitel")
                        title_text = title_el.get_text(separator=" ", strip=True) if title_el else a.get_text(separator=" ", strip=True)
                        detail_href = a.get("href") or ""
                    else:
                        title_h2 = td.find("h2", class_="filmtitel")
                        if title_h2:
                            title_text = title_h2.get_text(separator=" ", strip=True)

                    m = self.TIME_TITLE_RE.match(title_text)
                    if not m:
                        logger.debug("Skipping row, cannot parse time/title: %r", title_text)
                        continue

                    time_str = m.group("time")
                    film_title = m.group("title").strip()
                    film_title_lower = film_title.lower()

                    # Combine base_date with time
                    try:
                        hour, minute = map(int, time_str.split(":"))
                        dt = base_date.replace(hour=hour, minute=minute, second=0)
                    except Exception:
                        logger.debug("Invalid time %r for title %r", time_str, film_title)
                        continue

                    # Synopsis
                    synopsis_el = td.find("div", class_="filminhalt")
                    synopsis = synopsis_el.get_text(separator=" ", strip=True) if synopsis_el else ""

                    # Series / language note
                    note_el = td.find("div", class_="filmanmerkung")
                    note = note_el.get_text(separator=" ", strip=True) if note_el else ""
                    note_lower = note.lower() if note else ""

                    # Poster
                    img = td.find("img")
                    poster_url = urljoin(self.PAGE_URL, img["src"]) if img and img.get("src") else ""

                    # Ticket URL from form action
                    form = td.find("form")
                    ticket_url = form.get("action") if form and form.get("action") else ""
                    if ticket_url:
                        ticket_url = urljoin(self.PAGE_URL, ticket_url)

                    # Detail page
                    detail_url = urljoin(self.PAGE_URL, detail_href) if detail_href else ""

                    # Filter for OmU (site marks OmU shows in filmanmerkung)
                    if "omu-nachtstudio" not in note_lower:
                        logger.debug(
                            "Skipping non-OmU (filmanmerkung missing): %s (%s)",
                            film_title,
                            note,
                        )
                        continue

                    # Exclude known non-film shows like DESiMO
                    if any(b in note_lower for b in self.BLACKLIST) or any(b in film_title_lower for b in self.BLACKLIST):
                        logger.debug("Skipping blacklisted show: %s (%s)", film_title, note)
                        continue

                    # Choose event URL: prefer detail page, then ticket action, then page URL
                    event_url = detail_url or ticket_url or self.PAGE_URL

                    try:
                        metadata: dict[str, Any] = {
                            "synopsis": synopsis,
                            "original_version": True,
                            "poster_url": poster_url,
                        }

                        # If the show is within the movies lookahead, 
                        # fetch detail page to enrich metadata.
                        if detail_url and dt and dt.tzinfo is not None and now <= dt <= cutoff:
                            try:
                                detail_meta = self._fetch_detail_metadata(detail_url)
                                # Merge detail metadata (detail wins)
                                metadata.update(detail_meta)
                                # Be polite between requests
                                time.sleep(SCRAPE_DELAY_SECONDS)
                            except Exception:
                                logger.debug("Failed to fetch detail page %s for %s", detail_url, film_title)

                        ev = Event(
                            title=film_title,
                            date=dt,
                            venue=self.source_name,
                            url=event_url,
                            category="movie",
                            metadata=metadata,
                        )
                        events.append(ev)
                    except Exception as exc:
                        logger.debug("Skipping event due to validation error: %s", exc)

        logger.info("Apollokino: parsed %d events", len(events))
        return events

    def _parse_filmdaten(self, text: str) -> dict[str, Any]:
        """Parse the various filmdaten formats seen on Apollokino detail pages.

        Returns keys: country (str), year (int), duration (int minutes), rating (int), cast (list)
        """
        out: dict[str, Any] = {"country": "", "year": None, "duration": None, "rating": None, "cast": []}

        if not text:
            return out

        # Year
        year_m = re.search(r"(19|20)\d{2}", text)
        if year_m:
            try:
                out["year"] = int(year_m.group(0))
            except Exception:
                pass

        # Country - take leading segment before year or comma
        country_m = re.match(r"\s*([A-Za-zÄÖÜäöü0-9\-/ ,]+?)\s*(?:,|\b(19|20)\d{2}\b)", text)
        if country_m:
            country = country_m.group(1).strip()
            out["country"] = country

        # Duration
        dur_m = re.search(r"(?:Länge:|Länge|,|\s)(\d{2,3})\s*Min", text)
        if not dur_m:
            dur_m = re.search(r"(\d{2,3})\s*Min\.?", text)
        if dur_m:
            try:
                out["duration"] = int(dur_m.group(1))
            except Exception:
                pass

        # Rating: unify variants like "FSK 16", "FSK: 16", "ab 16 J.", etc.
        rating_m = re.search(r"(?:FSK[:\s]*|ab\s*)(\d{1,2})(?:\s*J\.?)*", text, re.IGNORECASE)
        if rating_m:
            try:
                out["rating"] = int(rating_m.group(1))
            except Exception:
                out["rating"] = None

        # Cast: non-greedy capture, stop before common trailing tokens like Länge:, FSK, R:
        cast_m = re.search(r"mit:\s*(.+?)(?=\s*(?:Länge:|FSK[:\s]|R:|$))", text, re.IGNORECASE)
        if cast_m:
            cast_text = cast_m.group(1)
            parts = [p.strip() for p in re.split(r",\s*|\s+und\s+", cast_text) if p.strip()]
            names: list[str] = []
            for p in parts:
                cleaned = self._clean_cast_name(p)
                if not cleaned:
                    continue
                # skip obvious stray tokens
                low = cleaned.lower()
                if low.startswith("länge") or low.startswith("fsk"):
                    continue
                names.append(cleaned)
            out["cast"] = names

        return out

    def _fetch_detail_metadata(self, url: str) -> dict[str, Any]:
        """Fetch detail page and extract metadata aligned with Astor's keys."""
        with create_http_client() as client:
            resp = client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

        return self._extract_metadata(soup)

    def _extract_metadata(self, soup: BeautifulSoup) -> dict[str, Any]:
        """Extract metadata from an Apollokino detail page soup.

        Returns keys: duration, rating, year, country, language, trailer_url, cast
        """
        out: dict[str, Any] = {}

        filmdaten_el = soup.find("div", class_="filmdaten")
        filmdaten_text = filmdaten_el.get_text(separator=" ", strip=True) if filmdaten_el else ""
        parsed = self._parse_filmdaten(filmdaten_text)

        homepage_el = soup.find("div", class_="filmhomepage")
        trailer_url = ""
        if homepage_el:
            a = homepage_el.find("a")
            if a and a.get("href"):
                trailer_url = a.get("href")

        if parsed.get("duration") is not None:
            out["duration"] = parsed["duration"]
            if parsed.get("rating") is not None:
                out["rating"] = parsed.get("rating")
        if parsed.get("year") is not None:
            out["year"] = parsed["year"]
        if parsed.get("country"):
            out["country"] = parsed["country"]
        out["language"] = self._derive_language_from_country(parsed.get("country", ""))
        if trailer_url:
            out["trailer_url"] = trailer_url
        if parsed.get("cast"):
            out["cast"] = parsed["cast"]

        # Detail synopsis
        filminhalt_el = soup.find("div", class_="filminhalt")
        if filminhalt_el:
            filminhalt_text = filminhalt_el.get_text(separator=" ", strip=True)
            if filminhalt_text:
                out["synopsis"] = filminhalt_text

        return out

    @staticmethod
    def _clean_cast_name(name: str) -> str:
        name = re.sub(r"\(.*?\)", "", name)
        name = name.replace("u.a.", "").replace("u.a", "")
        return name.strip().strip(",")

    @staticmethod
    def _derive_language_from_country(country: str) -> str:
        """Return a canonical German language string expected by the exporter.

        Behavior:
        - If `country` lists multiple countries (contains ',' or '/'), return only the
          subtitle token: "Untertitel: Deutsch" (we know Apollokino shows OmU).
        - For single-country codes (common short forms), return e.g.:
            "Sprache: Englisch, Untertitel: Deutsch"
        - If country is empty or unknown, return "Untertitel: Deutsch" since OmU implies
          German subtitles.
        """
        if not country:
            return "Untertitel: Deutsch"

        # If multiple countries listed, avoid guessing the spoken language
        if "," in country or "/" in country:
            return "Untertitel: Deutsch"

        c = country.strip().lower()
        # Map common short country codes to German language names
        code_map: dict[str, str] = {
            "usa": "Englisch",
            "us": "Englisch",
            "gb": "Englisch",
            "uk": "Englisch",
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
            "ie": "Englisch",
            "gr": "Griechisch",
            "tr": "Türkisch",
        }

        # Try exact matches first, then containment
        lang_name: str | None = None
        if c in code_map:
            lang_name = code_map[c]
        else:
            for key, name in code_map.items():
                if key in c:
                    lang_name = name
                    break

        if lang_name:
            return f"Sprache: {lang_name}, Untertitel: Deutsch"

        # Fallback: only subtitles (do not guess spoken language)
        return "Untertitel: Deutsch"
