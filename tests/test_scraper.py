"""Tests for BoringHannover scraper functionality.

Tests cover the core modules:
- models: Event dataclass and methods
- scrapers: Event fetching and parsing
- main: CLI and workflow orchestration
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from bs4 import BeautifulSoup

from boringhannover.aggregator import fetch_all_events
from boringhannover.constants import BERLIN_TZ
from boringhannover.models import Event
from boringhannover.notifier import format_message
from boringhannover.sources.base import BaseSource
from boringhannover.sources.cinema.apollokino import (
    ApollokinoSource as ApollokinoScraper,
)
from boringhannover.sources.cinema.astor import AstorSource as AstorMovieScraper
from boringhannover.sources.concerts.punkrock_konzerte import (
    PunkrockKonzerteSource,
)


if TYPE_CHECKING:
    from conftest import LocalSite

FIXTURES = Path(__file__).parent / "fixtures"


# =============================================================================
# Event Model Tests
# =============================================================================


class TestEventModel:
    """Tests for the Event dataclass."""

    def test_event_format_date_short(self) -> None:
        """Test short date formatting."""
        event = Event(
            title="Test",
            date=datetime(2024, 11, 24, 19, 30, tzinfo=BERLIN_TZ),
            venue="Venue",
            url="https://example.com",
            category="movie",
        )
        # Format: "Sun 24.11."  # noqa: ERA001
        result = event.format_date_short()
        assert "24.11." in result

    def test_event_format_time(self) -> None:
        """Test time formatting."""
        event = Event(
            title="Test",
            date=datetime(2024, 11, 24, 19, 30, tzinfo=BERLIN_TZ),
            venue="Venue",
            url="https://example.com",
            category="movie",
        )
        result = event.format_time()
        assert "19:30" in result

    def test_event_is_this_week(self) -> None:
        """Test this week detection."""
        today = datetime.now(BERLIN_TZ)
        tomorrow = today + timedelta(days=1)
        next_month = today + timedelta(days=30)

        event_this_week = Event(
            title="This Week",
            date=tomorrow,
            venue="Venue",
            url="https://example.com",
            category="movie",
        )
        event_next_month = Event(
            title="Next Month",
            date=next_month,
            venue="Venue",
            url="https://example.com",
            category="movie",
        )

        assert event_this_week.is_this_week() is True
        assert event_next_month.is_this_week() is False

    def test_event_normalizes_naive_datetime_to_berlin_tz(self) -> None:
        """Naive datetimes are treated as Europe/Berlin."""
        naive = datetime(2025, 12, 12, 19, 30)  # noqa: DTZ001
        event = Event(
            title="Naive Date",
            date=naive,
            venue="Venue",
            url="https://example.com",
            category="movie",
        )
        assert event.date.tzinfo is BERLIN_TZ
        assert (event.date.hour, event.date.minute) == (19, 30)


class TestAstorMovieScraper:
    def test_fetch_keeps_original_versions_and_drops_german_dubs(
        self, local_site: LocalSite
    ) -> None:
        local_site.pages["/program"] = (
            200,
            json.dumps(
                {
                    "genres": [{"id": 1, "name": "Drama"}],
                    "movies": [
                        {
                            "id": 100,
                            "name": "Test Movie",
                            "minutes": 120,
                            "rating": 12,
                            "year": 2024,
                            "country": "US",
                            "genreIds": [1],
                        }
                    ],
                    "performances": [
                        {
                            "movieId": 100,
                            "begin": "2024-11-24T19:30:00",
                            "language": "Sprache: Englisch",
                        },
                        {
                            "movieId": 100,
                            "begin": "2024-11-24T22:00:00",
                            "language": "Sprache: Deutsch",
                        },
                    ],
                }
            ),
        )

        class LocalAstor(AstorMovieScraper):
            API_URL = f"{local_site.url}/program"

        result = LocalAstor().fetch()

        assert len(result) == 1
        assert result[0].title == "Test Movie"
        assert result[0].date.hour == 19
        assert result[0].metadata["duration"] == 120
        assert result[0].metadata["genres"] == ["Drama"]


class TestPunkrockKonzerteSource:
    """Tests for the Punkrock-Konzerte scraper."""

    def test_parse_events_skips_lux_covered_by_first_party_source(self) -> None:
        html = """
        <div class="row bg_gig result" itemscope itemtype="http://schema.org/Event">
            <div class="col-md-2 col-sm-2 col-xs-12">
                <div class="dateBox">
                    22.01.2099 <meta itemprop="startDate" content="2099-01-22" />
                </div>
            </div>
            <div class="col-md-8 col-sm-8 col-xs-12">
                <div class="row">
                    <div class="col-md-12 small">
                        <span itemprop="location" itemscope itemtype="http://schema.org/MusicVenue">
                            <span itemprop="address">Hannover</span> -
                            <span itemprop="name">LUX</span>
                        </span>
                    </div>
                    <div class="col-md-12">
                        <span class="b" itemprop="name">Test Band</span>
                    </div>
                </div>
            </div>
            <div class="lnkBtn">
                <a class="info" href="https://example.com/event" title="Mehr Infos"></a>
            </div>
        </div>
        <div class="row bg_gig result" itemscope itemtype="http://schema.org/Event">
            <div class="col-md-2 col-sm-2 col-xs-12">
                <div class="dateBox">23.02.2099</div>
            </div>
            <div class="col-md-8 col-sm-8 col-xs-12">
                <div class="row">
                    <div class="col-md-12 small">
                        <span itemprop="location" itemscope itemtype="http://schema.org/MusicVenue">
                            <span itemprop="address">Hannover</span> -
                            <span itemprop="name">Bei Chez Heinz</span>
                        </span>
                    </div>
                    <div class="col-md-12">
                        <span class="b" itemprop="name">Another Band</span>
                    </div>
                </div>
            </div>
        </div>
        <div class="row bg_gig result" itemscope itemtype="http://schema.org/Event">
            <div class="col-md-2 col-sm-2 col-xs-12">
                <div class="dateBox">
                    01.01.2000 <meta itemprop="startDate" content="2000-01-01" />
                </div>
            </div>
            <div class="col-md-8 col-sm-8 col-xs-12">
                <div class="row">
                    <div class="col-md-12 small">
                        <span itemprop="location" itemscope itemtype="http://schema.org/MusicVenue">
                            <span itemprop="address">Hannover</span> -
                            <span itemprop="name">Faust</span>
                        </span>
                    </div>
                    <div class="col-md-12">
                        <span class="b" itemprop="name">Past Band</span>
                    </div>
                </div>
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")

        source = PunkrockKonzerteSource()
        events = source._parse_events(soup)

        assert len(events) == 1
        assert events[0].title == "Another Band"
        assert events[0].venue == "Bei Chez Heinz"
        assert events[0].metadata["address"] == "Hannover"
        assert events[0].metadata["time"] == "20:00"


class TestApollokinoScraper:
    """Tests for the Apollokino scraper."""

    @staticmethod
    def _serve(local_site: LocalSite, html: str) -> type[ApollokinoScraper]:
        local_site.pages["/?mp=OmU-Nachtstudio"] = (200, html)

        class LocalApollokino(ApollokinoScraper):
            PAGE_URL = f"{local_site.url}/?mp=OmU-Nachtstudio"

        return LocalApollokino

    def test_fetch_parses_omu_entries(self, local_site: LocalSite) -> None:
        html = (FIXTURES / "apollokino_omu.html").read_text(encoding="utf-8")

        result = self._serve(local_site, html)().fetch()

        assert len(result) > 0
        ev = result[0]
        assert ev.category == "movie"
        assert ev.title == "THE MASTERMIND"
        assert ev.date.strftime("%H:%M") == "22:30"
        assert ev.metadata["poster_url"].endswith("/filme/00005138/plakat00005138.jpg")
        assert ev.url.endswith("/?v=&film=filme/00005138&anmerk=OmU-Nachtstudio")
        assert ev.metadata.get("original_version") is True

    def test_fetch_rejects_non_omu_and_blacklist(self, local_site: LocalSite) -> None:
        """Rows without the OmU marker or with Desimo/Spezial Club must be skipped."""
        html = """
        <div class="datumzeile">Freitag, 02.01.2026</div>
        <table class="filmtabelle"><tr><td>
          <table class="tagestabelle">
            <tr><td>
              <a href="/?v=&film=filme/00001"><h2 class="filmtitel">22:30: Ein Film</h2></a>
              <div class="filmanmerkung">Premiere</div>
            </td></tr>
            <tr><td>
              <a href="/?v=&film=filme/00002"><h2 class="filmtitel">23:00: DESiMO Spezial</h2></a>
              <div class="filmanmerkung">OmU-Nachtstudio</div>
            </td></tr>
            <tr><td>
              <a href="/?v=&film=filme/00003"><h2 class="filmtitel">22:30: Echter Film</h2></a>
              <div class="filmanmerkung">OmU-Nachtstudio</div>
            </td></tr>
          </table>
        </td></tr></table>
        """

        result = self._serve(local_site, html)().fetch()

        assert [e.title for e in result] == ["Echter Film"]

    def test_extract_metadata_from_detail_soup(self) -> None:
        """Detail extraction works directly from a parsed soup (no HTTP)."""
        soup = BeautifulSoup(
            (FIXTURES / "apollokino_detail.html").read_text(encoding="utf-8"),
            "html.parser",
        )

        meta = ApollokinoScraper()._extract_metadata(soup)

        assert meta["duration"] == 124
        assert meta["rating"] == 16
        assert meta["year"] == 1975
        assert meta["country"].lower().startswith("usa")
        assert meta["language"] == "Sprache: Englisch, Untertitel: Deutsch"
        assert meta["trailer_url"] == "https://www.youtube.com/watch?v=bBBBbadAkwM"
        assert {"role": "Regie", "name": "Steven Spielberg"} in meta["cast"]
        assert {"role": "Darsteller", "name": "Roy Scheider"} in meta["cast"]
        assert "Steven Spiebergs Hai-Blockbuster" in meta["synopsis"]
        assert "Lexikon des internationalen Films" in meta["synopsis"]

    def test_detail_fetch_failure_returns_empty(self, local_site: LocalSite) -> None:
        """A failed detail fetch must degrade gracefully, never raise."""
        meta = ApollokinoScraper()._fetch_detail_metadata(f"{local_site.url}/missing")
        assert meta == {}

    def test_parse_filmdaten_handles_messy_text(self) -> None:
        """Live filmdaten has price hints and double colons; parser must cope."""
        text = (
            "GB 2026, 134 Min. (+-,50€), ab 16 J., "
            "R:  Emerald Fennell, mit: : Margot Robbie, Jacob Elordi, Hong Chau u.a."
        )
        parsed = ApollokinoScraper()._parse_filmdaten(text)
        assert parsed["year"] == 2026
        assert parsed["duration"] == 134
        assert parsed["rating"] == 16
        assert parsed["country"] == "GB"
        assert {"role": "Regie", "name": "Emerald Fennell"} in parsed["cast"]
        assert {"role": "Darsteller", "name": "Margot Robbie"} in parsed["cast"]
        assert {"role": "Darsteller", "name": "Jacob Elordi"} in parsed["cast"]
        # Trailing "u.a." must be stripped from the last actor name.
        assert {"role": "Darsteller", "name": "Hong Chau"} in parsed["cast"]
        assert not any("u.a" in entry["name"].lower() for entry in parsed["cast"])

    def test_parse_filmdaten_without_cast(self) -> None:
        """Director regex must stop at Länge:/FSK: when no `mit:` follows."""
        text = "DE 2024, R: Wim Wenders, Länge: 99 Min., FSK 12"
        parsed = ApollokinoScraper()._parse_filmdaten(text)
        assert parsed["cast"] == [{"role": "Regie", "name": "Wim Wenders"}]

    @pytest.mark.parametrize(
        ("country", "expected"),
        [
            ("USA", "Sprache: Englisch, Untertitel: Deutsch"),
            ("GB", "Sprache: Englisch, Untertitel: Deutsch"),
            ("JP", "Sprache: Japanisch, Untertitel: Deutsch"),
            ("Deutschland", "Sprache: Deutsch, Untertitel: Deutsch"),
            ("Großbritannien", "Sprache: Englisch, Untertitel: Deutsch"),
            ("Polen", "Sprache: Polnisch, Untertitel: Deutsch"),
            # Regression: "at" inside "australien" must NOT match the AT code.
            ("Australien", "Sprache: Englisch, Untertitel: Deutsch"),
            # Multi-country: never guess spoken language.
            ("GB/F", "Untertitel: Deutsch"),
            ("Deutschland, Frankreich", "Untertitel: Deutsch"),
            # Unknown country: subtitle-only fallback.
            ("Atlantis", "Untertitel: Deutsch"),
            ("", "Untertitel: Deutsch"),
        ],
    )
    def test_derive_language_from_country(self, country: str, expected: str) -> None:
        assert ApollokinoScraper._derive_language_from_country(country) == expected


class TestFetchAllEvents:
    """Tests for the event aggregation function."""

    def test_handles_naive_datetimes_from_sources(self) -> None:
        """Sources may emit naive datetimes; aggregation should not crash."""
        today = datetime.now(BERLIN_TZ)

        class StaticSource(BaseSource):
            source_name = "Static"
            source_type = "cinema"

            def fetch(self) -> list[Event]:
                return [
                    Event(
                        title="Movie",
                        date=(today + timedelta(days=1)).replace(tzinfo=None),
                        venue="Venue",
                        url="https://example.com",
                        category="movie",
                    ),
                    Event(
                        title="Concert",
                        date=(today + timedelta(days=8)).replace(tzinfo=None),
                        venue="Venue",
                        url="https://example.com",
                        category="radar",
                    ),
                ]

        result = fetch_all_events(sources={"static": StaticSource})

        assert [e.title for e in result["movies_this_week"]] == ["Movie"]
        assert [e.title for e in result["big_events_radar"]] == ["Concert"]


# =============================================================================
# Notifier Tests
# =============================================================================


class TestFormatMessage:
    """Tests for message formatting."""

    def test_format_message_includes_sections(self) -> None:
        """Test that formatted message includes all sections."""
        test_data = {
            "movies_this_week": [],
            "big_events_radar": [],
        }
        result = format_message(test_data)

        assert "Movies" in result
        assert "Radar" in result

    def test_format_message_with_movies(self) -> None:
        """Test formatting with movie events."""
        movie = Event(
            title="Inception",
            date=datetime(2024, 11, 24, 19, 30, tzinfo=BERLIN_TZ),
            venue="Astor Grand Cinema",
            url="https://example.com",
            category="movie",
            metadata={"duration": 148, "year": 2010, "language": "Sprache: Englisch"},
        )
        test_data = {
            "movies_this_week": [movie],
            "big_events_radar": [],
        }
        result = format_message(test_data)

        assert "Inception" in result
        assert "2010" in result
        assert "19:30" in result

    def test_format_message_with_concerts(self) -> None:
        """Test formatting with concert events."""
        concert = Event(
            title="Rock Concert",
            date=datetime(2024, 12, 15, 20, 0, tzinfo=BERLIN_TZ),
            venue="ZAG Arena",
            url="https://example.com",
            category="radar",
            metadata={"time": "20:00"},
        )
        test_data = {
            "movies_this_week": [],
            "big_events_radar": [concert],
        }
        result = format_message(test_data)

        assert "Rock Concert" in result
        assert "ZAG Arena" in result
        assert "20:00" in result

    def test_format_message_handles_empty_data(self) -> None:
        """Test that empty data is handled gracefully."""
        test_data = {
            "movies_this_week": [],
            "big_events_radar": [],
        }
        result = format_message(test_data)

        assert "No OV movies" in result
