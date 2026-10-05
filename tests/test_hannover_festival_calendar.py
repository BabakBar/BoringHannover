"""Tests for official City Occasion discovery."""

from __future__ import annotations

import json
import logging
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup

from boringhannover.occasions import OccasionDefinition
from boringhannover.sources import get_source
from boringhannover.sources.base import create_http_client
from boringhannover.sources.festivals.hannover_calendar import (
    HannoverFestivalCalendarSource,
)


if TYPE_CHECKING:
    from collections.abc import Iterator


FIXTURES = Path(__file__).parent / "fixtures"
LISTING_PATH = "/Veranstaltungskalender/Feste-Festivals"
LOAD_MORE_PATH = "/api/v1/view/533295/10/10/line"
PAGE3_PATH = "/api/v1/view/533295/20/10/line"
LOAD_MORE_IDENTIFIERS = (
    "article,government_service,organisation,article,file_video,route,"
    "teaserlink,contact,file_audio,image,file,link,event,gallery,folder,"
    "frontpage,iframe,searchable_external_link,undertaking,microsite_with_zones"
)
OFFICIAL_LISTING_URL = f"https://www.hannover.de{LISTING_PATH}"


class FixtureServer:
    """Real local HTTP server replaying captured hannover.de responses."""

    def __init__(self) -> None:
        self.routes: dict[str, tuple[int, str, bytes]] = {}
        self.requests: list[str] = []
        routes, requests = self.routes, self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                requests.append(self.path)
                status, content_type, body = routes.get(
                    urlparse(self.path).path, (404, "text/plain", b"")
                )
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args: object) -> None:
                return

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever)

    def url(self, path: str) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host!s}:{port}{path}"

    def serve_fixture(self, path: str, fixture: str, content_type: str) -> None:
        self.routes[path] = (200, content_type, (FIXTURES / fixture).read_bytes())

    def serve_json(self, path: str, payload: object) -> None:
        self.routes[path] = (200, "application/json", json.dumps(payload).encode())

    def __enter__(self) -> FixtureServer:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join()


@pytest.fixture
def calendar_server() -> Iterator[FixtureServer]:
    with FixtureServer() as server:
        server.serve_fixture(
            LISTING_PATH, "hannover_festivals_listing.html", "text/html"
        )
        yield server


def _card_titles(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    return [
        " ".join(title.get_text(" ", strip=True).split())
        for title in soup.select(
            "article.interesting-single.line-view-content .interesting-single__title"
        )
    ]


def _page2_items() -> list[str]:
    payload = json.loads(
        (FIXTURES / "hannover_festivals_page2.json").read_text(encoding="utf-8")
    )
    return payload["items"]


def _summary(location: str) -> OccasionDefinition:
    return OccasionDefinition(
        id="hannover-festivals:kiezkultur-festival",
        slug="kiezkultur-festival",
        name="KiezKultur Festival",
        kind="festival",
        start_date=date(2026, 10, 9),
        end_date=date(2026, 10, 10),
        location=location,
        source_url=f"{OFFICIAL_LISTING_URL}/KiezKultur-Festival",
        description="Zwei Tage Kiezkultur.",
    )


def test_parse_calendar_discovers_city_occasions_and_excludes_region() -> None:
    source = HannoverFestivalCalendarSource()
    html = (FIXTURES / "hannover_festivals.html").read_text(encoding="utf-8")

    occasions = source._parse_calendar(html)

    assert [occasion.slug for occasion in occasions] == [
        "maschseefest-hannover-2026",
        "fahrmannsfest-2026",
    ]

    maschseefest = occasions[0]
    assert maschseefest.start_date == date(2026, 7, 23)
    assert maschseefest.end_date == date(2026, 8, 9)
    assert maschseefest.location == "Maschseefest"
    assert maschseefest.image_url.endswith("/maschsee-large.jpg")
    assert maschseefest.source_url.startswith("https://www.hannover.de/")

    faehrmannsfest = occasions[1]
    assert faehrmannsfest.start_date == date(2026, 7, 31)
    assert faehrmannsfest.end_date == date(2026, 7, 31)
    assert faehrmannsfest.description.startswith("Das alternative")


def test_discovery_source_is_registered_without_timeline_events() -> None:
    source_class = get_source("hannover_festival_calendar")

    assert source_class is HannoverFestivalCalendarSource
    assert source_class.source_type == "occasion"
    assert source_class().fetch() == []


def test_parse_detail_end_date_uses_final_official_appointment() -> None:
    end_date = HannoverFestivalCalendarSource._parse_detail_end_date(
        """
        <div class="details">
          <div class="detail-row">
            <div class="detail-cell"><p>Termine</p></div>
            <div class="detail-cell">
              <p>31.07.2026 ab 16:30 Uhr</p>
              <p>01.08.2026 ab 15:00 Uhr</p>
              <p>02.08.2026 ab 15:30 Uhr</p>
            </div>
          </div>
        </div>
        """
    )

    assert end_date == date(2026, 8, 2)


def test_fetch_calendar_html_follows_load_more_until_last_page(
    calendar_server: FixtureServer,
) -> None:
    calendar_server.serve_fixture(
        LOAD_MORE_PATH, "hannover_festivals_page2.json", "application/json"
    )
    source = HannoverFestivalCalendarSource()

    with create_http_client() as client:
        html = source._fetch_calendar_html(client, calendar_server.url(LISTING_PATH))

    assert _card_titles(html) == [
        "Oktoberfest 2026",
        "KiezKultur Festival",
        "Hannover Wies'n",
        "Nacht der Museen 2027",
        "Schützenfest Hannover 2027",
        "Klassik Open Air: Operngala im Maschpark",
        "Ent\xaddecker\xadtag der Region Hannover 2027",
    ]
    load_more_request = urlparse(calendar_server.requests[1])
    assert load_more_request.path == LOAD_MORE_PATH
    assert "identifiers=article" in load_more_request.query
    assert "sortField=2" in load_more_request.query
    assert "sortOrder=1" in load_more_request.query
    assert len(calendar_server.requests) == 2


def test_fetch_calendar_html_follows_three_pages_and_dedupes_cards(
    calendar_server: FixtureServer,
) -> None:
    items = _page2_items()
    calendar_server.serve_json(
        LOAD_MORE_PATH,
        {"success": True, "items": items[:2], "next": PAGE3_PATH, "isLast": False},
    )
    calendar_server.serve_json(
        PAGE3_PATH,
        {"success": True, "items": items[1:], "next": None, "isLast": True},
    )
    source = HannoverFestivalCalendarSource()

    with create_http_client() as client:
        html = source._fetch_calendar_html(client, calendar_server.url(LISTING_PATH))

    requests = [urlparse(request) for request in calendar_server.requests]
    assert [request.path for request in requests] == [
        LISTING_PATH,
        LOAD_MORE_PATH,
        PAGE3_PATH,
    ]
    expected_query = {
        "identifiers": [LOAD_MORE_IDENTIFIERS],
        "sortField": ["2"],
        "sortOrder": ["1"],
    }
    assert parse_qs(requests[1].query) == expected_query
    assert parse_qs(requests[2].query) == expected_query

    assert _card_titles(html).count("Schützenfest Hannover 2027") == 2
    assert [occasion.slug for occasion in source._parse_calendar(html)] == [
        "oktoberfest-2026",
        "hannover-wies-27n",
        "kiezkultur-festival",
        "nacht-der-museen-2027",
        "schutzenfest-hannover-2027",
        "klassik-open-air-operngala-im-maschpark",
    ]


def test_fetch_calendar_html_keeps_first_page_when_load_more_fails(
    calendar_server: FixtureServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calendar_server.routes[LOAD_MORE_PATH] = (500, "text/plain", b"")
    source = HannoverFestivalCalendarSource()

    with (
        caplog.at_level(logging.WARNING),
        create_http_client() as client,
    ):
        html = source._fetch_calendar_html(client, calendar_server.url(LISTING_PATH))

    assert _card_titles(html) == [
        "Oktoberfest 2026",
        "KiezKultur Festival",
        "Hannover Wies'n",
    ]
    assert "pagination stopped" in caplog.text


def test_fetch_calendar_html_stops_at_page_limit(
    calendar_server: FixtureServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calendar_server.serve_json(
        LOAD_MORE_PATH,
        {"success": True, "items": [], "next": LOAD_MORE_PATH, "isLast": False},
    )
    source = HannoverFestivalCalendarSource()

    with (
        caplog.at_level(logging.WARNING),
        create_http_client() as client,
    ):
        source._fetch_calendar_html(client, calendar_server.url(LISTING_PATH))

    load_more_requests = [
        request
        for request in calendar_server.requests
        if urlparse(request).path == LOAD_MORE_PATH
    ]
    assert len(load_more_requests) == source.MAX_LOAD_MORE_PAGES
    assert "truncated" in caplog.text


def test_parse_load_more_page_returns_cards_and_stops_on_last_page() -> None:
    payload = json.loads(
        (FIXTURES / "hannover_festivals_page2.json").read_text(encoding="utf-8")
    )

    html, next_url = HannoverFestivalCalendarSource._parse_load_more_page(
        payload, f"https://www.hannover.de{LOAD_MORE_PATH}"
    )

    assert len(_card_titles(html)) == 4
    assert next_url is None


def test_parse_load_more_page_resolves_next_page_on_same_origin() -> None:
    _html, next_url = HannoverFestivalCalendarSource._parse_load_more_page(
        {
            "success": True,
            "items": [],
            "next": "/api/v1/view/533295/20/10/line",
            "isLast": False,
        },
        f"https://www.hannover.de{LOAD_MORE_PATH}?identifiers=event",
    )

    assert next_url == "https://www.hannover.de/api/v1/view/533295/20/10/line"


@pytest.mark.parametrize(
    "payload",
    [
        {"success": False, "items": [], "next": None, "isLast": True},
        {"success": True, "items": "<article></article>", "isLast": True},
        {"success": True, "items": [42], "isLast": True},
    ],
)
def test_parse_load_more_page_rejects_malformed_payloads(payload: object) -> None:
    with pytest.raises(ValueError, match="load-more"):
        HannoverFestivalCalendarSource._parse_load_more_page(
            payload, f"https://www.hannover.de{LOAD_MORE_PATH}"
        )


@pytest.mark.parametrize(
    "raw_next",
    [
        "https://example.com/api/v1/view/533295/20/10/line",
        "/Veranstaltungskalender/Feste-Festivals",
        "/api/v1/view/999999/20/10/line",
        "/api/v1/view/533295/20/10/tile",
        "/api/v1/view/533295/20/50/line",
        "/api/v1/view/533295/20/10/line/extra",
    ],
)
def test_parse_load_more_page_keeps_cards_when_next_url_leaves_the_view(
    raw_next: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    items = _page2_items()[:1]

    with caplog.at_level(logging.WARNING):
        html, next_url = HannoverFestivalCalendarSource._parse_load_more_page(
            {"success": True, "items": items, "next": raw_next, "isLast": False},
            f"https://www.hannover.de{LOAD_MORE_PATH}",
        )

    assert _card_titles(html) == ["Nacht der Museen 2027"]
    assert next_url is None
    assert raw_next in caplog.text


def test_parse_calendar_keeps_cards_without_listing_location() -> None:
    source = HannoverFestivalCalendarSource()
    html = (FIXTURES / "hannover_festivals_listing.html").read_text(encoding="utf-8")

    occasions = {occasion.slug: occasion for occasion in source._parse_calendar(html)}

    assert occasions["kiezkultur-festival"].location == ""
    assert occasions["oktoberfest-2026"].location == "Schützenplatz Hannover"


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        (
            "hannover_festival_detail_kiezkultur.html",
            "Zur Bettfedernfabrik 3, 30451 Hannover",
        ),
        (
            "hannover_festival_detail_tiergartenfest.html",
            "Tiergarten, Tiergartenstraße 117, 30559 Hannover",
        ),
    ],
)
def test_parse_detail_location_reads_official_ort_row(
    fixture: str,
    expected: str,
) -> None:
    html = (FIXTURES / fixture).read_text(encoding="utf-8")

    assert HannoverFestivalCalendarSource._parse_detail_location(html) == expected


def test_apply_detail_fills_missing_location_from_ort_row() -> None:
    html = (FIXTURES / "hannover_festival_detail_kiezkultur.html").read_text(
        encoding="utf-8"
    )

    occasion = HannoverFestivalCalendarSource._apply_detail(_summary(""), html)

    assert occasion.location == "Zur Bettfedernfabrik 3, 30451 Hannover"
    assert occasion.end_date == date(2026, 10, 10)


def test_apply_detail_keeps_listing_location() -> None:
    html = (FIXTURES / "hannover_festival_detail_kiezkultur.html").read_text(
        encoding="utf-8"
    )

    occasion = HannoverFestivalCalendarSource._apply_detail(_summary("Faust"), html)

    assert occasion.location == "Faust"


@pytest.mark.parametrize(
    ("location", "publishable"),
    [
        ("Zur Bettfedernfabrik 3, 30451 Hannover", True),
        ("", False),
        ("Hauptstraße 1, 30974 Wennigsen", False),
    ],
)
def test_is_publishable_requires_a_city_location(
    location: str,
    publishable: bool,
) -> None:
    assert (
        HannoverFestivalCalendarSource._is_publishable(_summary(location))
        is publishable
    )
