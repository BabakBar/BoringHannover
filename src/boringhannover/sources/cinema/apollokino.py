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
import re
from datetime import datetime
from typing import ClassVar
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
                        ev = Event(
                            title=film_title,
                            date=dt,
                            venue=self.source_name,
                            url=event_url,
                            category="movie",
                            metadata={
                                "synopsis": synopsis,
                                "original_version": True,
                                "poster_url": poster_url,
                            },
                        )
                        events.append(ev)
                    except Exception as exc:
                        logger.debug("Skipping event due to validation error: %s", exc)

        logger.info("Apollokino: parsed %d events", len(events))
        return events
