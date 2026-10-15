"""Official City Occasion discovery: listing, pagination and detail pages."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from bs4 import BeautifulSoup

from boringhannover.aggregator import fetch_all_events
from boringhannover.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from boringhannover.occasions import OccasionDefinition
from boringhannover.source_outcomes import SourceOutcome
from boringhannover.sources.base import create_http_client
from boringhannover.sources.festivals.hannover_calendar import (
    HannoverFestivalCalendarSource,
)


if TYPE_CHECKING:
    from collections.abc import Callable

    from conftest import LocalSite


SOURCE = HannoverFestivalCalendarSource
FIXTURES = Path(__file__).parent / "fixtures"
LISTING_PATH = "/Veranstaltungskalender/Feste-Festivals"
LOAD_MORE_PATH = "/api/v1/view/533295/10/10/line"
PAGE3_PATH = "/api/v1/view/533295/20/10/line"
LOAD_MORE_QUERY = {
    "identifiers": [
        "article,government_service,organisation,article,file_video,route,"
        "teaserlink,contact,file_audio,image,file,link,event,gallery,folder,"
        "frontpage,iframe,searchable_external_link,undertaking,microsite_with_zones"
    ],
    "sortField": ["2"],
    "sortOrder": ["1"],
}
OFFICIAL_LOAD_MORE_URL = f"https://www.hannover.de{LOAD_MORE_PATH}"
# The heading of the live listing page (15 Oct 2026), without any cards.
EMPTY_LISTING = (
    '<html><body><h1 class="content-detail__title">Feste &amp; Festivals</h1>'
    "</body></html>"
)


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _page2_items() -> list[str]:
    return json.loads(_fixture("hannover_festivals_page2.json"))["items"]


def _card_titles(html: str) -> list[str]:
    return [
        " ".join(title.get_text(" ", strip=True).split())
        for title in BeautifulSoup(html, "html.parser").select(
            "article.interesting-single.line-view-content .interesting-single__title"
        )
    ]


def _calendar_html(local_site: LocalSite) -> tuple[str, list[str]]:
    local_site.pages[LISTING_PATH] = (200, _fixture("hannover_festivals_listing.html"))
    with create_http_client() as client:
        return SOURCE()._fetch_calendar_html(client, f"{local_site.url}{LISTING_PATH}")


def _summary(location: str, source_summary: str = "") -> OccasionDefinition:
    return OccasionDefinition(
        id="hannover-festivals:kiezkultur-festival",
        slug="kiezkultur-festival",
        name="KiezKultur Festival",
        kind="festival",
        start_date=date(2026, 10, 9),
        end_date=date(2026, 10, 10),
        location=location,
        source_url="https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/KiezKultur-Festival",
        description="",
        source_summary=source_summary or "Zwei Tage Kiezkultur.",
    )


def test_captured_listing_discovers_city_occasions_and_excludes_region() -> None:
    occasions, unread = SOURCE()._parse_calendar(_fixture("hannover_festivals.html"))

    # The Langenhagen card is filtered out, which leaves nothing unread.
    assert unread == []
    assert [occasion.slug for occasion in occasions] == [
        "maschseefest-hannover-2026",
        "fahrmannsfest-2026",
    ]
    maschseefest, faehrmannsfest = occasions

    assert maschseefest.start_date == date(2026, 7, 23)
    assert maschseefest.end_date == date(2026, 8, 9)
    assert maschseefest.location == "Maschseefest"
    assert maschseefest.source_url.startswith("https://www.hannover.de/")

    assert faehrmannsfest.start_date == date(2026, 7, 31)
    assert faehrmannsfest.end_date == date(2026, 7, 31)
    # The German teaser is evidence only; English copy is chosen at export.
    assert faehrmannsfest.source_summary.startswith("Das alternative")
    assert faehrmannsfest.description == ""

    listing = {
        occasion.slug: occasion
        for occasion in SOURCE()._parse_calendar(
            _fixture("hannover_festivals_listing.html")
        )[0]
    }
    # A card without a listed location is kept for detail enrichment.
    assert listing["kiezkultur-festival"].location == ""
    assert listing["oktoberfest-2026"].location == "Schützenplatz Hannover"


def test_follows_load_more_until_the_last_page(local_site: LocalSite) -> None:
    local_site.pages[LOAD_MORE_PATH] = (200, _fixture("hannover_festivals_page2.json"))

    html, gaps = _calendar_html(local_site)

    assert gaps == []
    assert _card_titles(html) == [
        "Oktoberfest 2026",
        "KiezKultur Festival",
        "Hannover Wies'n",
        "Nacht der Museen 2027",
        "Schützenfest Hannover 2027",
        "Klassik Open Air: Operngala im Maschpark",
        "Ent\xaddecker\xadtag der Region Hannover 2027",
    ]
    assert len(local_site.requests) == 2
    load_more = urlsplit(local_site.requests[1])
    assert load_more.path == LOAD_MORE_PATH
    assert parse_qs(load_more.query) == LOAD_MORE_QUERY


def test_follows_three_pages_and_dedupes_cards(local_site: LocalSite) -> None:
    items = _page2_items()
    local_site.pages[LOAD_MORE_PATH] = (
        200,
        json.dumps(
            {"success": True, "items": items[:2], "next": PAGE3_PATH, "isLast": False}
        ),
    )
    local_site.pages[PAGE3_PATH] = (
        200,
        json.dumps({"success": True, "items": items[1:], "next": None, "isLast": True}),
    )

    html, gaps = _calendar_html(local_site)

    assert gaps == []
    requests = [urlsplit(request) for request in local_site.requests]
    assert [request.path for request in requests] == [
        LISTING_PATH,
        LOAD_MORE_PATH,
        PAGE3_PATH,
    ]
    assert parse_qs(requests[2].query) == LOAD_MORE_QUERY
    assert _card_titles(html).count("Schützenfest Hannover 2027") == 2
    assert [occasion.slug for occasion in SOURCE()._parse_calendar(html)[0]] == [
        "oktoberfest-2026",
        "hannover-wies-27n",
        "kiezkultur-festival",
        "nacht-der-museen-2027",
        "schutzenfest-hannover-2027",
        "klassik-open-air-operngala-im-maschpark",
    ]


def test_failed_load_more_keeps_the_first_page(
    local_site: LocalSite, caplog: pytest.LogCaptureFixture
) -> None:
    local_site.pages[LOAD_MORE_PATH] = (500, "")

    with caplog.at_level(logging.WARNING):
        html, gaps = _calendar_html(local_site)

    assert _card_titles(html) == [
        "Oktoberfest 2026",
        "KiezKultur Festival",
        "Hannover Wies'n",
    ]
    (gap,) = gaps
    assert gap.startswith("pagination stopped after 1 pages: HTTPStatusError")
    assert gap in caplog.text


def test_pagination_stops_at_the_page_limit(local_site: LocalSite) -> None:
    local_site.pages[LOAD_MORE_PATH] = (
        200,
        json.dumps(
            {"success": True, "items": [], "next": LOAD_MORE_PATH, "isLast": False}
        ),
    )

    _, gaps = _calendar_html(local_site)

    load_more_requests = [
        request
        for request in local_site.requests
        if urlsplit(request).path == LOAD_MORE_PATH
    ]
    assert len(load_more_requests) == SOURCE.MAX_LOAD_MORE_PAGES
    assert gaps == [
        "pagination stopped after 11 pages: "
        "ValueError: page limit reached before the last page"
    ]


@pytest.mark.parametrize(
    ("payload", "card_count", "next_url"),
    [
        (json.loads(_fixture("hannover_festivals_page2.json")), 4, None),
        (
            {"success": True, "items": [], "next": PAGE3_PATH, "isLast": False},
            0,
            PAGE3_PATH,
        ),
    ],
)
def test_load_more_page(
    payload: dict[str, object], card_count: int, next_url: str | None
) -> None:
    items = SOURCE._load_more_items(payload)

    assert len(_card_titles("\n".join(items))) == card_count
    assert SOURCE._load_more_next(payload) == next_url


@pytest.mark.parametrize(
    "payload",
    [
        {"success": False, "items": [], "next": None, "isLast": True},
        {"success": True, "items": "<article></article>", "isLast": True},
        {"success": True, "items": [42], "isLast": True},
    ],
)
def test_malformed_load_more_page_is_rejected(payload: object) -> None:
    with pytest.raises(ValueError, match="load-more"):
        SOURCE._load_more_items(payload)


@pytest.mark.parametrize(
    "payload",
    [
        # Neither the last page nor a way on: not a confirmed end.
        {"success": True, "items": [], "isLast": False},
        {"success": True, "items": [], "next": None},
    ],
)
def test_missing_continuation_is_not_an_end(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="load-more next URL"):
        SOURCE._load_more_next(payload)


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
def test_next_url_leaving_the_view_stops_but_keeps_cards(
    local_site: LocalSite, raw_next: str
) -> None:
    local_site.pages[LOAD_MORE_PATH] = (
        200,
        json.dumps(
            {
                "success": True,
                "items": _page2_items()[:1],
                "next": raw_next,
                "isLast": False,
            }
        ),
    )

    html, gaps = _calendar_html(local_site)

    assert _card_titles(html)[-1] == "Nacht der Museen 2027"
    assert len(local_site.requests) == 2
    (gap,) = gaps
    assert gap.startswith("pagination stopped after 2 pages: ValueError")
    assert raw_next in gap


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
def test_detail_location_reads_the_official_ort_row(
    fixture: str, expected: str
) -> None:
    assert SOURCE._parse_detail_location(_fixture(fixture)) == expected


@pytest.mark.parametrize(
    ("listing_location", "expected"),
    [
        ("", "Zur Bettfedernfabrik 3, 30451 Hannover"),
        ("Faust", "Faust"),
    ],
)
def test_detail_fills_only_a_missing_location(
    listing_location: str, expected: str
) -> None:
    occasion = SOURCE._apply_detail(
        _summary(listing_location),
        _fixture("hannover_festival_detail_kiezkultur.html"),
    )

    assert occasion.location == expected
    assert occasion.end_date == date(2026, 10, 10)


@pytest.mark.parametrize(
    ("location", "publishable"),
    [
        ("Zur Bettfedernfabrik 3, 30451 Hannover", True),
        ("", False),
        ("Hauptstraße 1, 30974 Wennigsen", False),
    ],
)
def test_publishing_requires_a_city_location(location: str, publishable: bool) -> None:
    assert SOURCE._is_publishable(_summary(location)) is publishable


def test_listing_teaser_still_excludes_the_region() -> None:
    occasion = _summary("Hof Müller", "Das Hoffest in Springe lädt ein.")

    assert SOURCE._is_publishable(occasion) is False


def test_detail_keeps_a_rescheduling_proven_by_the_listing_teaser() -> None:
    (listing,), _ = SOURCE()._parse_calendar(
        """
        <article class="interesting-single line-view-content">
          <h3 class="interesting-single__title">Verschoben: X-Fest</h3>
          <span class="date__duration">12.07.2026</span>
          <span class="date__category">Swiss Life Hall</span>
          <div class="interesting-single__description"><p>Das Konzert wird
            vom 30. Juni 2026 auf den 12. Juli 2026 verschoben.</p></div>
          <a class="content__read-more"
             href="/Veranstaltungskalender/Feste-Festivals/X-Fest">mehr</a>
        </article>
        """
    )

    occasion = SOURCE._apply_detail(listing, "<html></html>")

    assert occasion.source_status == "rescheduled"
    assert occasion.previous_start_date == date(2026, 6, 30)
    assert occasion.description == ""


def test_calendar_identifies_itself_while_other_sources_keep_the_shared_agent(
    local_site: LocalSite,
) -> None:
    local_site.pages[LISTING_PATH] = (200, EMPTY_LISTING)

    class LocalCalendar(SOURCE):
        CALENDAR_URL = f"{local_site.url}{LISTING_PATH}"

    assert LocalCalendar().discover_occasions() == []
    with create_http_client() as client:
        client.get(f"{local_site.url}{LISTING_PATH}").raise_for_status()

    agent = SOURCE.USER_AGENT
    assert local_site.user_agents == [agent, USER_AGENT]
    assert agent.startswith("BoringHannover (+https://boringhannover.de/impressum/;")
    # Only the header changes: timeout and redirects stay shared.
    with create_http_client(user_agent=agent) as client:
        assert client.follow_redirects is True
        assert client.timeout == httpx.Timeout(REQUEST_TIMEOUT_SECONDS)


DETAIL_PAGES = {
    "/Veranstaltungskalender/Feste-Festivals/Oktoberfest-2026": (
        "hannover_festival_detail_oktoberfest.html"
    ),
    "/Veranstaltungskalender/Feste-Festivals/KiezKultur-Festival": (
        "hannover_festival_detail_kiezkultur.html"
    ),
    "/Veranstaltungskalender/Feste-Festivals/Hannover-Wies%27n": (
        "hannover_festival_detail_wiesn.html"
    ),
}
LAST_PAGE = json.dumps({"success": True, "items": [], "isLast": True})
LISTING_SLUGS = ["oktoberfest-2026", "hannover-wies-27n", "kiezkultur-festival"]


def _serve_listing(
    local_site: LocalSite, listing: str | None = None, load_more: str = LAST_PAGE
) -> None:
    """Serve the captured three-card listing, its last page and its details."""
    local_site.pages[LISTING_PATH] = (
        200,
        listing or _fixture("hannover_festivals_listing.html"),
    )
    local_site.pages[LOAD_MORE_PATH] = (200, load_more)
    for path, fixture in DETAIL_PAGES.items():
        local_site.pages[path] = (200, _fixture(fixture))


def _unreadable_card(local_site: LocalSite) -> None:
    listing = _fixture("hannover_festivals_listing.html")
    _serve_listing(
        local_site, listing.replace("09.10.2026 bis 10.10.2026", "Termin folgt")
    )


def _pages_never_end(local_site: LocalSite) -> None:
    _serve_listing(
        local_site,
        load_more=json.dumps(
            {"success": True, "items": [], "next": LOAD_MORE_PATH, "isLast": False}
        ),
    )


def _undetailed_unlocated_card(local_site: LocalSite) -> None:
    _serve_listing(local_site)
    del local_site.pages["/Veranstaltungskalender/Feste-Festivals/KiezKultur-Festival"]


def _maintenance_detail_for_unlocated_card(local_site: LocalSite) -> None:
    _serve_listing(local_site)
    local_site.pages["/Veranstaltungskalender/Feste-Festivals/KiezKultur-Festival"] = (
        200,
        "<html><body>Wartungsarbeiten</body></html>",
    )


def _undetailed_located_card(local_site: LocalSite) -> None:
    _serve_listing(local_site)
    del local_site.pages["/Veranstaltungskalender/Feste-Festivals/Oktoberfest-2026"]


@pytest.mark.parametrize(
    ("serve", "state", "slugs", "completion", "reason"),
    [
        pytest.param(
            _serve_listing, "success", LISTING_SLUGS, "complete", "", id="complete"
        ),
        # Missing optional details keep a located occasion and the inventory whole.
        pytest.param(
            _undetailed_located_card,
            "success",
            LISTING_SLUGS,
            "complete",
            "",
            id="details-optional",
        ),
        pytest.param(
            lambda site: site.pages.update({LISTING_PATH: (200, EMPTY_LISTING)}),
            "empty",
            [],
            "complete",
            "",
            id="empty-season",
        ),
        pytest.param(
            lambda site: site.pages.update({LISTING_PATH: (503, "")}),
            "failed",
            [],
            "incomplete",
            "HTTPStatusError: Server error '503 Service Unavailable'",
            id="listing-request-fails",
        ),
        pytest.param(
            lambda site: site.pages.update(
                {LISTING_PATH: (200, "<html><body>Wartungsarbeiten</body></html>")}
            ),
            "failed",
            [],
            "incomplete",
            "ValueError: Response is not the festival listing",
            id="not-the-listing",
        ),
        pytest.param(
            lambda site: _serve_listing(site, load_more="not json"),
            "partial",
            LISTING_SLUGS,
            "incomplete",
            "pagination stopped after 1 pages: JSONDecodeError",
            id="later-page-malformed",
        ),
        pytest.param(
            _pages_never_end,
            "partial",
            LISTING_SLUGS,
            "incomplete",
            "pagination stopped after 11 pages: ValueError: page limit reached",
            id="page-limit",
        ),
        pytest.param(
            _unreadable_card,
            "partial",
            ["oktoberfest-2026", "hannover-wies-27n"],
            "incomplete",
            "1 listing entries unreadable",
            id="unreadable-card",
        ),
        pytest.param(
            _undetailed_unlocated_card,
            "partial",
            ["oktoberfest-2026", "hannover-wies-27n"],
            "incomplete",
            "1 occasions without a location",
            id="unlocated-without-details",
        ),
        # A 200 page that is not a detail page leaves the location just as unknown.
        pytest.param(
            _maintenance_detail_for_unlocated_card,
            "partial",
            ["oktoberfest-2026", "hannover-wies-27n"],
            "incomplete",
            "1 occasions without a location",
            id="unlocated-with-unreadable-details",
        ),
        # Content the parser cannot read is not an empty page.
        pytest.param(
            lambda site: _serve_listing(
                site,
                load_more=json.dumps(
                    {
                        "success": True,
                        "items": ["<div>unrecognized listing markup</div>"],
                        "isLast": True,
                    }
                ),
            ),
            "partial",
            LISTING_SLUGS,
            "incomplete",
            "page 2: 1 of 1 entries unreadable",
            id="later-page-unreadable",
        ),
        # A broken continuation keeps the cards of the page that carried it.
        pytest.param(
            lambda site: _serve_listing(
                site,
                load_more=json.dumps(
                    {
                        "success": True,
                        "items": _page2_items()[1:2],
                        "next": None,
                        "isLast": False,
                    }
                ),
            ),
            "partial",
            [*LISTING_SLUGS, "schutzenfest-hannover-2027"],
            "incomplete",
            "pagination stopped after 2 pages: ValueError: Malformed load-more next URL",
            id="malformed-continuation-keeps-its-page",
        ),
    ],
)
def test_discovery_outcome_tells_empty_from_failed_and_partial(
    local_site: LocalSite,
    serve: Callable[[LocalSite], None],
    state: str,
    slugs: list[str],
    completion: str,
    reason: str,
) -> None:
    """Aggregation keeps every occasion read and says how much that was."""
    serve(local_site)

    class LocalCalendar(SOURCE):
        CALENDAR_URL = f"{local_site.url}{LISTING_PATH}"

    result = fetch_all_events(sources={"festivals": LocalCalendar})

    fetched, discovered = result["source_outcomes"]
    # The source never fetches timeline events, so its empty fetch is normal
    # and says nothing about discovery.
    assert fetched == SourceOutcome("festivals", "fetch", "empty", 0, "unknown")
    assert (discovered.operation, discovered.state) == ("discover_occasions", state)
    assert discovered.completion == completion
    assert discovered.count == len(slugs)
    assert discovered.reason.startswith(reason)
    assert [occasion.slug for occasion in result.get("city_occasions", [])] == slugs
    # Occasions keep their public hannover.de URLs; only requests went local.
    assert all(
        occasion.source_url.startswith("https://www.hannover.de/")
        for occasion in result.get("city_occasions", [])
    )
