"""Source parsing: each source turns a captured or minimal page into Events."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from bs4 import BeautifulSoup

from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import CONFIRMED_TIME, FALLBACK_TIME
from boringhannover.sources.cinema.apollokino import ApollokinoSource
from boringhannover.sources.cinema.astor import AstorSource
from boringhannover.sources.concerts.broncos import BroncosSource
from boringhannover.sources.concerts.faust import FaustSource
from boringhannover.sources.concerts.glocke import GlockseeSource
from boringhannover.sources.concerts.kulturpalast_linden import (
    KulturpalastLindenSource,
)
from boringhannover.sources.concerts.lux import LuxSource
from boringhannover.sources.concerts.platzprojekt import PlatzprojektSource
from boringhannover.sources.concerts.punkrock_konzerte import (
    PunkrockKonzerteSource,
)
from boringhannover.sources.concerts.weltspiele import WeltspieleSource
from boringhannover.sources.sports.hannover_96 import Hannover96Source


if TYPE_CHECKING:
    from conftest import LocalSite


FIXTURES = Path(__file__).parent / "fixtures"
SOURCES_DIR = Path(__file__).parents[1] / "src" / "boringhannover" / "sources"
NOW = datetime(2026, 7, 26, 12, 0, tzinfo=BERLIN_TZ)

# Real LUX description that used to publish as "...das ebenfalls de".
LONG_DESCRIPTION = (
    "Sean Koch kehrt mit einem brandneuen Album und einer noch nie dagewesenen "
    "Show nach Europa zurück. Die „Time Will Tell“-Tour feiert die "
    "Veröffentlichung von Seans drittem Studioalbum, das ebenfalls denselben "
    "Namen trägt."
)


def test_every_source_module_is_discovered_and_registered() -> None:
    """A source the registry never sees silently disappears from the site."""
    expected = sorted(
        ".".join(
            (
                "boringhannover",
                *path.relative_to(SOURCES_DIR.parent).with_suffix("").parts,
            )
        )
        for path in SOURCES_DIR.glob("*/*.py")
        if "@register_source(" in path.read_text(encoding="utf-8")
    )
    # A fresh interpreter, so registration comes from discovery alone.
    registered = subprocess.run(
        [
            sys.executable,
            "-c",
            "from boringhannover.sources import get_all_sources; "
            "print(*sorted({c.__module__ for c in get_all_sources().values()}))",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()

    assert registered == expected


def _soup(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / name).read_text(encoding="utf-8"), "html.parser")


def test_astor_keeps_original_versions_and_drops_german_dubs(
    local_site: LocalSite,
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

    class LocalAstor(AstorSource):
        API_URL = f"{local_site.url}/program"

    events = LocalAstor().fetch()

    assert len(events) == 1
    assert events[0].title == "Test Movie"
    assert events[0].date.hour == 19
    assert events[0].metadata["duration"] == 120
    assert events[0].metadata["genres"] == ["Drama"]
    assert events[0].metadata["language"] == "Sprache: Englisch"


class TestApollokino:
    @staticmethod
    def _fetch(local_site: LocalSite, html: str) -> list:
        local_site.pages["/?mp=OmU-Nachtstudio"] = (200, html)

        class LocalApollokino(ApollokinoSource):
            PAGE_URL = f"{local_site.url}/?mp=OmU-Nachtstudio"

        return LocalApollokino().fetch()

    def test_parses_captured_omu_page(self, local_site: LocalSite) -> None:
        html = (FIXTURES / "apollokino_omu.html").read_text(encoding="utf-8")

        event = self._fetch(local_site, html)[0]

        assert event.category == "movie"
        assert event.title == "THE MASTERMIND"
        assert event.date.strftime("%H:%M") == "22:30"
        assert event.metadata["poster_url"].endswith(
            "/filme/00005138/plakat00005138.jpg"
        )
        assert event.url.endswith("/?v=&film=filme/00005138&anmerk=OmU-Nachtstudio")
        assert event.metadata["original_version"] is True

    def test_rejects_rows_without_omu_marker_and_blacklisted_hosts(
        self, local_site: LocalSite
    ) -> None:
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

        assert [e.title for e in self._fetch(local_site, html)] == ["Echter Film"]

    def test_detail_page_metadata(self) -> None:
        meta = ApollokinoSource()._extract_metadata(_soup("apollokino_detail.html"))

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

    def test_failed_detail_fetch_degrades_to_no_metadata(
        self, local_site: LocalSite
    ) -> None:
        meta = ApollokinoSource()._fetch_detail_metadata(f"{local_site.url}/missing")

        assert meta == {}

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (
                # Live filmdaten: price hint, double colon, trailing "u.a.".
                "GB 2026, 134 Min. (+-,50€), ab 16 J., "
                "R:  Emerald Fennell, mit: : Margot Robbie, Jacob Elordi, Hong Chau u.a.",
                {
                    "year": 2026,
                    "duration": 134,
                    "rating": 16,
                    "country": "GB",
                    "cast": [
                        {"role": "Regie", "name": "Emerald Fennell"},
                        {"role": "Darsteller", "name": "Margot Robbie"},
                        {"role": "Darsteller", "name": "Jacob Elordi"},
                        {"role": "Darsteller", "name": "Hong Chau"},
                    ],
                },
            ),
            (
                # Director must stop at "Länge:" when no "mit:" follows.
                "DE 2024, R: Wim Wenders, Länge: 99 Min., FSK 12",
                {"cast": [{"role": "Regie", "name": "Wim Wenders"}]},
            ),
        ],
    )
    def test_filmdaten(self, text: str, expected: dict) -> None:
        parsed = ApollokinoSource()._parse_filmdaten(text)

        assert {key: parsed[key] for key in expected} == expected

    @pytest.mark.parametrize(
        ("country", "expected"),
        [
            ("USA", "Sprache: Englisch, Untertitel: Deutsch"),
            ("GB", "Sprache: Englisch, Untertitel: Deutsch"),
            ("JP", "Sprache: Japanisch, Untertitel: Deutsch"),
            ("Deutschland", "Sprache: Deutsch, Untertitel: Deutsch"),
            ("Großbritannien", "Sprache: Englisch, Untertitel: Deutsch"),
            ("Polen", "Sprache: Polnisch, Untertitel: Deutsch"),
            # "at" inside "australien" must not match the AT code.
            ("Australien", "Sprache: Englisch, Untertitel: Deutsch"),
            # Several countries or an unknown one: never guess the language.
            ("GB/F", "Untertitel: Deutsch"),
            ("Deutschland, Frankreich", "Untertitel: Deutsch"),
            ("Atlantis", "Untertitel: Deutsch"),
            ("", "Untertitel: Deutsch"),
        ],
    )
    def test_language_from_country(self, country: str, expected: str) -> None:
        assert ApollokinoSource._derive_language_from_country(country) == expected


def _broncos_card(
    *, href: str | None, start: str | None, title: str | None, tagline: str = ""
) -> str:
    inner = "".join(
        [
            f'<time class="event__start-time" datetime="{start}">x</time>'
            if start
            else "",
            f'<h3 class="event__title">{title}</h3>' if title else "",
            f'<span class="event__tagline">{tagline}</span>' if tagline else "",
        ]
    )
    if href is None:
        return f'<article class="event">{inner}</article>'
    return f'<article class="event"><a class="event__link" href="{href}">{inner}</a></article>'


class TestBroncos:
    @staticmethod
    def _fetch(local_site: LocalSite, cards: list[str]) -> list:
        local_site.pages["/ort/broncos"] = (200, "".join(cards))

        class LocalBroncos(BroncosSource):
            URL = f"{local_site.url}/ort/broncos"

        return LocalBroncos().fetch()

    def test_parses_cards_and_skips_incomplete_ones(
        self, local_site: LocalSite
    ) -> None:
        events = self._fetch(
            local_site,
            [
                _broncos_card(
                    href="/event/test?date=2026-01-23",
                    start="2026-01-23T20:00:00+01:00",
                    title="Test Band",
                    tagline="Elektronische Musik",
                ),
                _broncos_card(
                    href="/event/big-honey",
                    start="2026-02-15T20:00:00+00:00",
                    title="Guest Night",
                    tagline="Mit Big Honey",
                ),
                _broncos_card(
                    href=None, start="2026-01-23T20:00:00+01:00", title="No Link"
                ),
                _broncos_card(href="/event/no-time", start=None, title="No Time"),
                _broncos_card(
                    href="/event/no-title",
                    start="2026-01-23T20:00:00+01:00",
                    title=None,
                ),
                _broncos_card(
                    href="/event/bad-date", start="2026-13-45", title="Bad Date"
                ),
            ],
        )

        assert [
            (e.title, e.date.hour, e.metadata["genre"], e.metadata["genre_source"])
            for e in events
        ] == [
            ("Test Band", 20, "Electronic", "stadtkind_tagline"),
            # UTC converted to Berlin; descriptive billing is not a genre.
            ("Guest Night", 21, "", ""),
        ]
        band = events[0]
        assert band.venue == "Broncos"
        assert band.category == "radar"
        assert (
            band.url == "https://www.stadtkind-kalender.de/event/test?date=2026-01-23"
        )
        assert band.metadata["time"] == "20:00"
        assert band.metadata["address"] == "Schwarzer Bär 7, 30449 Hannover"

    def test_stops_at_max_events(self, local_site: LocalSite) -> None:
        cards = [
            _broncos_card(
                href=f"/event/{i}",
                start=f"2026-01-{(i % 28) + 1:02d}T20:00:00+01:00",
                title=f"Event {i}",
            )
            for i in range(50)
        ]

        assert len(self._fetch(local_site, cards)) == BroncosSource.max_events == 40


def _ics(*events: list[str]) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Test//EN"]
    for event in events:
        lines += ["BEGIN:VEVENT", *event, "END:VEVENT"]
    return "\n".join([*lines, "END:VCALENDAR"])


class TestKulturpalastLinden:
    @staticmethod
    def _fetch(local_site: LocalSite, ics: str) -> list:
        local_site.pages["/events/?ical=1"] = (200, ics)

        class LocalKulturpalast(KulturpalastLindenSource):
            ICAL_URL = f"{local_site.url}/events/?ical=1"

        return LocalKulturpalast().fetch()

    def test_parses_feed_and_repairs_or_drops_broken_entries(
        self, local_site: LocalSite
    ) -> None:
        events = self._fetch(
            local_site,
            _ics(
                [
                    "DTSTART:20260130T200000",
                    "SUMMARY:Later Event",
                ],
                [
                    "DTSTART;TZID=Europe/Berlin:20260124T200000",
                    "DTEND;TZID=Europe/Berlin:20260124T230000",
                    "SUMMARY:Test Event",
                    "DESCRIPTION:Line 1\\nLine 2",
                    "URL:https://example.com/event",
                ],
                # Ends "before" it starts on the same date: a cross-midnight
                # party the feed writes wrongly. Must be repaired, not lost.
                [
                    "DTSTART:20260125T220000",
                    "DTEND:20260125T020000",
                    "SUMMARY:Late Night Party",
                    f"DESCRIPTION:{LONG_DESCRIPTION}",
                ],
                # Ends on an earlier day: unrecoverable, dropped alone.
                [
                    "DTSTART:20260126T220000",
                    "DTEND:20260125T020000",
                    "SUMMARY:Invalid Event",
                ],
                ["DTSTART:20260127T200000", "SUMMARY:"],
                ["DTSTART;VALUE=DATE:20260128", "SUMMARY:All Day Event"],
            ),
        )

        assert [e.title for e in events] == [
            "Test Event",
            "Late Night Party",
            "All Day Event",
            "Later Event",
        ]
        test_event, party, all_day, later = events
        assert test_event.url == "https://example.com/event"
        assert test_event.venue == "Kulturpalast Linden"
        assert test_event.metadata["description"] == "Line 1"
        assert test_event.metadata["time"] == "20:00"
        assert party.metadata["description"].endswith("ebenfalls…")
        assert all_day.date.date().isoformat() == "2026-01-28"
        assert later.url == "https://kulturpalast-hannover.de/events/"

    def test_malformed_feed_yields_nothing(self, local_site: LocalSite) -> None:
        assert self._fetch(local_site, "not valid ics data at all") == []


class TestWeltspiele:
    def test_fetch_reads_event_pages_and_falls_back_without_them(
        self, local_site: LocalSite
    ) -> None:
        local_site.pages["/programm/"] = (
            200,
            """
            <div class="program-month">
              <div class="program-month-title">Januar</div>
              <a href="/event/confirmed"><li class="program-event">
                <div class="program-event-header"><span class="in-brackets">Fr 23</span></div>
                <span class="program-event-tag">Party</span>
                <div class="underline underline-rich-text-box">Support Act</div>
                <div class="underline">Listing Title</div>
                <div class="program-event-place">
                  <span class="underline-rich-text-box">DJ One</span>
                  <span class="underline-rich-text-box">DJ Two</span>
                </div>
              </li></a>
              <a href="/event/no-time"><li class="program-event">
                <div class="program-event-header"><span class="in-brackets">Sa 24</span></div>
                <span class="program-event-tag">Club</span>
                <div class="underline">No Time</div>
              </li></a>
              <a href="/event/broken"><li class="program-event">
                <div class="program-event-header"><span class="in-brackets">So 25</span></div>
                <div class="underline">Broken Page</div>
              </li></a>
              <li class="program-event">
                <div class="program-event-header"><span class="in-brackets">Mo 26</span></div>
                <div class="underline">Orphan Event</div>
              </li>
            </div>
            """,
        )
        local_site.pages["/event/confirmed"] = (
            200,
            '<h1 class="event-title">Page Title</h1>'
            '<div class="show-date">Fr 23 Januar 23:30-06:00</div>',
        )
        local_site.pages["/event/no-time"] = (200, "<p>No show-date here</p>")

        class LocalWeltspiele(WeltspieleSource):
            PROGRAM_URL = f"{local_site.url}/programm/"
            BASE_URL = local_site.url

        events = LocalWeltspiele().fetch()

        assert [
            (e.title, e.date.month, e.date.day, e.metadata["time"]) for e in events
        ] == [
            ("Page Title", 1, 23, "23:30"),
            ("No Time", 1, 24, "22:00"),
            ("Broken Page", 1, 25, "22:00"),
        ]
        confirmed, no_time, broken = events
        assert confirmed.metadata["time_confidence"] == CONFIRMED_TIME
        assert confirmed.metadata["subtitle"] == "DJ One DJ Two"
        assert confirmed.metadata["event_type"] == "Party"
        assert no_time.metadata["time_confidence"] == FALLBACK_TIME
        assert no_time.url == f"{local_site.url}/event/no-time"
        assert broken.url == LocalWeltspiele.PROGRAM_URL
        assert broken.metadata["event_type"] == "club"

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Sat 27 January 22:00-10:00", (1, 27, 22, 0)),
            ("Sa 15 Februar 21:00", (2, 15, 21, 0)),
            ("", None),
            ("No date here", None),
            ("27 January", None),
        ],
    )
    def test_show_date(self, text: str, expected: tuple | None) -> None:
        parsed = WeltspieleSource()._parse_show_date(text)

        assert (
            (parsed.month, parsed.day, parsed.hour, parsed.minute) if parsed else None
        ) == expected


class TestPunkrockKonzerte:
    def test_skips_lux_and_past_gigs(self) -> None:
        def gig(date_box: str, venue: str, title: str) -> str:
            return f"""
            <div class="row bg_gig result" itemscope itemtype="http://schema.org/Event">
              <div class="dateBox">{date_box}</div>
              <span itemprop="location" itemscope itemtype="http://schema.org/MusicVenue">
                <span itemprop="address">Hannover</span> - <span itemprop="name">{venue}</span>
              </span>
              <span class="b" itemprop="name">{title}</span>
              <div class="lnkBtn"><a class="info" href="https://example.com/event"></a></div>
            </div>
            """

        html = "".join(
            [
                # LUX is covered by its first-party source.
                gig(
                    '22.01.2099 <meta itemprop="startDate" content="2099-01-22" />',
                    "LUX",
                    "Test Band",
                ),
                gig("23.02.2099", "Bei Chez Heinz", "Another Band"),
                gig(
                    '01.01.2000 <meta itemprop="startDate" content="2000-01-01" />',
                    "Faust",
                    "Past Band",
                ),
            ]
        )

        events = PunkrockKonzerteSource()._parse_events(
            BeautifulSoup(html, "html.parser")
        )

        assert [(e.title, e.venue) for e in events] == [
            ("Another Band", "Bei Chez Heinz")
        ]
        assert events[0].metadata["address"] == "Hannover"
        assert events[0].metadata["time"] == "20:00"

    @pytest.mark.parametrize(
        ("fixture", "titles", "venue", "address"),
        [
            (
                "stumpf_event.html",
                ["Fearskaper"],
                PunkrockKonzerteSource.STUMPF_VENUE,
                PunkrockKonzerteSource.STUMPF_ADDRESS,
            ),
            (
                "sv_arminia_events.html",
                ["Labasheeda + die ueblichen", "Muck And The Mires"],
                PunkrockKonzerteSource.ARMINIA_VENUE,
                PunkrockKonzerteSource.ARMINIA_ADDRESS,
            ),
        ],
    )
    def test_venue_aliases_get_the_official_name_and_address(
        self, fixture: str, titles: list[str], venue: str, address: str
    ) -> None:
        events = PunkrockKonzerteSource()._parse_events(_soup(fixture))

        assert [e.title for e in events] == titles
        assert {e.venue for e in events} == {venue}
        assert {e.metadata["address"] for e in events} == {address}

    def test_kulturpalast_detail_page_start_time(self) -> None:
        result = PunkrockKonzerteSource()._parse_kulturpalast_datetime(
            '<script type="application/ld+json">'
            '[{"@type":"Event","startDate":"2026-07-07T20:00:00+02:00"}]'
            "</script>"
        )

        assert result == datetime(2026, 7, 7, 20, 0, tzinfo=BERLIN_TZ)


def test_lux_captured_programme() -> None:
    events = LuxSource()._parse_events(_soup("lux_programme.html"), now=NOW)

    # Cancelled, unresolved, past and malformed entries are dropped.
    assert [event.title for event in events] == [
        "DRIVEN BY CLOCKWORK /W SUMMER GLOOM",
        "PON DE BEATS X RAMUNE RAVE",
        "MC BOMBER",
        "JANUARY FUTURE",
    ]
    concert, club_night, sold_out, future = events

    assert concert.date == datetime(2026, 8, 14, 20, 0, tzinfo=BERLIN_TZ)
    assert concert.url.endswith("/konzerte/driven-by-clockwork-w-summer-gloom/")
    assert concert.venue == "LUX"
    assert concert.metadata["time_confidence"] == CONFIRMED_TIME
    assert concert.metadata["event_type"] == "concert"
    assert concert.metadata["status"] == "available"
    assert concert.metadata["genre"] == "Punk / Hardcore"
    assert concert.metadata["genre_source"] == "programme_description"
    assert concert.metadata["price"] == "16 € zzgl. Geb."
    assert concert.metadata["address"] == "Schwarzer Bär 2, 30449 Hannover"
    assert concert.metadata["image_url"].endswith("/driven.jpg")

    assert club_night.date == datetime(2026, 8, 22, 22, 0, tzinfo=BERLIN_TZ)
    assert club_night.metadata["event_type"] == "party"
    assert "genre" not in club_night.metadata

    assert sold_out.metadata["status"] == "sold_out"
    assert "price" not in sold_out.metadata

    # January is next year's January.
    assert future.date == datetime(2027, 1, 21, 20, 30, tzinfo=BERLIN_TZ)
    assert future.metadata["genre"] == "Rock"


class TestPlatzprojekt:
    def test_captured_payload(self) -> None:
        source = PlatzprojektSource()
        payload = json.loads(
            (FIXTURES / "platzprojekt_events.json").read_text(encoding="utf-8")
        )

        events = source._parse_payload(payload, now=NOW)

        assert [event.title for event in events] == [
            "PLATZkino – heute mit „Parasite“",  # noqa: RUF001
            "Blaue Zone Sommercamp",
            "Offenes Krökeln",
        ]
        timed, all_day, default_venue = events

        assert timed.date == datetime(2026, 7, 28, 20, 0, tzinfo=BERLIN_TZ)
        assert timed.venue == "OSCO – OpenSpace"  # noqa: RUF001
        assert timed.category == "radar"
        assert timed.metadata == {
            "time": "20:00",
            "time_confidence": CONFIRMED_TIME,
            "end_time": "23:00",
            "event_type": "event",
            "subtitle": "Jeden vierten Dienstag findet das PLATZkino statt.",
            "description": "Jeden vierten Dienstag findet das PLATZkino statt.",
            "image_url": (
                "https://platzprojekt.de/wp-content/uploads/2026/07/platzkino.jpg"
            ),
            "address": "Fössestr. 103, 30453 Hannover",
            "price": "5 €",
            "source_name": "PLATZprojekt",
        }

        assert all_day.date == datetime(2026, 7, 30, 12, 0, tzinfo=BERLIN_TZ)
        assert all_day.metadata["time_confidence"] == FALLBACK_TIME
        assert all_day.metadata["end_time"] == ""

        assert default_venue.venue == source.source_name
        assert default_venue.metadata["address"] == source.ADDRESS

    @pytest.mark.parametrize("payload", [[], {"events": "invalid"}])
    def test_malformed_payload_yields_nothing(self, payload: object) -> None:
        assert PlatzprojektSource()._parse_payload(payload, now=NOW) == []


def test_hannover_96_captured_calendar() -> None:
    source = Hannover96Source()
    calendar = (FIXTURES / "hannover_96_matches.ics").read_text(encoding="utf-8")

    events = source._parse_calendar(calendar, now=NOW)

    # Only future public home matches with a kickoff.
    assert [event.title for event in events] == [
        "Hannover 96 vs. VfL Wolfsburg",
        "Hannover 96 vs. Phönix Lübeck",
    ]
    league_match, friendly = events

    assert league_match.date == datetime(2026, 8, 16, 13, 30, tzinfo=BERLIN_TZ)
    assert league_match.venue == "Heinz von Heiden Arena"
    assert league_match.category == "radar"
    assert league_match.url == source.SCHEDULE_URL
    assert league_match.metadata == {
        "time": "13:30",
        "time_confidence": CONFIRMED_TIME,
        "event_type": "sport",
        "competition": "2. Bundesliga",
        "opponent": "VfL Wolfsburg",
        "address": source.ARENA_ADDRESS,
    }

    assert friendly.date == datetime(2026, 8, 18, 18, 0, tzinfo=BERLIN_TZ)
    assert friendly.venue == "Eilenriedestadion"
    assert friendly.metadata["competition"] == "Testspiel"
    assert "address" not in friendly.metadata

    assert source._expand_opponent("XYZ") == "XYZ"


@pytest.mark.parametrize(
    ("lines", "expected_start", "expected_time", "confidence"),
    [
        (["Beginn: 19:30 Uhr"], (2, 19, 30), "19:30", CONFIRMED_TIME),
        (["Einlass / Beginn: 14 Uhr"], (2, 14, 0), "14:00", CONFIRMED_TIME),
        # Label and hour split across lines.
        (["Einlass / Beginn:", "23 Uhr"], (2, 23, 0), "23:00", CONFIRMED_TIME),
        # "24 Uhr" stays on its own day and sorts after every evening show.
        (["Einlass / Beginn: 24 Uhr"], (2, 23, 59), "24:00", CONFIRMED_TIME),
        # No start time: keep the placeholder, never display it.
        (["Eintritt frei"], (2, 20, 0), "20:00", FALLBACK_TIME),
    ],
)
def test_faust_start_times(
    lines: list[str],
    expected_start: tuple[int, int, int],
    expected_time: str,
    confidence: str,
) -> None:
    spans = "".join(f"<span>{line}</span>" for line in lines)
    link = BeautifulSoup(
        '<a href="/veranstaltungen/oktober/021026-puro-barrio.html">'
        f"<span>Fr, 02.10.26</span><span>Puro Barrio</span>{spans}</a>",
        "html.parser",
    ).a
    assert link is not None

    event = FaustSource()._parse_event(link, event_type="party")

    assert event is not None
    assert event.title == "Puro Barrio"
    assert (event.date.day, event.date.hour, event.date.minute) == expected_start
    assert event.metadata["time"] == expected_time
    assert event.metadata["time_confidence"] == confidence


class TestGlocksee:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (None, "concert"),
            ("", "concert"),
            ("Konzert", "concert"),
            (" KONZERT ", "concert"),
            ("party", "party"),
        ],
    )
    def test_event_type(self, raw: object, expected: str) -> None:
        now = datetime.now(BERLIN_TZ)
        data: dict[str, object] = {
            "title": [{"text": "Test Show"}],
            "datetime": (now + timedelta(days=3)).isoformat(),
        }
        if raw is not None:
            data["event_type"] = raw

        event = GlockseeSource()._parse_event({"uid": "x", "data": data}, now)

        assert event is not None
        assert event.metadata["event_type"] == expected

    def test_start_time_comes_from_beginn_not_einlass(self) -> None:
        result = GlockseeSource()._extract_confirmed_time(
            {
                "info_list": [
                    {"info": "Einlass 20.00 Uhr"},
                    {"info": "Beginn 21.15 Uhr"},
                    {"info": "Eintritt frei"},
                ]
            }
        )

        assert result == (21, 15)
