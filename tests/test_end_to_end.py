"""Scrape -> aggregate -> export -> production Astro build, on today's dates.

Sources fetch from a localhost server, so the whole pipeline runs its real
code without the network. Needs the frontend dependencies (`bun install` in
web/); CI installs them in the frontend job.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from bs4 import BeautifulSoup

from boringhannover.aggregator import fetch_all_events
from boringhannover.constants import BERLIN_TZ
from boringhannover.exporters import export_web_json
from boringhannover.github_sync import carry_forward_occasions
from boringhannover.models import Event
from boringhannover.occasions import OccasionDefinition, Occurrence, Place
from boringhannover.sources.cinema.astor import AstorSource
from boringhannover.sources.concerts.kulturpalast_linden import (
    KulturpalastLindenSource,
)
from boringhannover.sources.festivals.hannover_calendar import (
    HannoverFestivalCalendarSource,
)
from conftest import serve_christmas_calendar, serve_github_publication


if TYPE_CHECKING:
    from conftest import LocalSite


WEB = Path(__file__).parents[1] / "web"
ASTRO = WEB / "node_modules" / "astro" / "bin" / "astro.mjs"
BUN = shutil.which("bun")

pytestmark = pytest.mark.skipif(
    BUN is None or not ASTRO.exists(),
    reason="needs bun and web/node_modules (run `bun install` in web/)",
)


@pytest.mark.parametrize("rediscovered", [False, True], ids=["omitted", "rediscovered"])
def test_known_ended_occasions_reach_retained_pages_without_active_discovery(
    rediscovered: bool, local_site: LocalSite, tmp_path: Path
) -> None:
    now = datetime.now(BERLIN_TZ)
    root = tmp_path / "output"
    root.mkdir()
    definitions = [
        OccasionDefinition(
            id=f"retained:{offset}",
            slug=f"retained-{offset}",
            name=f"Retained festival {offset}",
            kind="festival",
            start_date=now.date() - timedelta(days=10),
            end_date=now.date() - timedelta(days=offset),
            location="Hannover",
            source_url=f"https://example.com/retained-{offset}",
            description="Source-supported festival details.",
            schedule_confidence="discrete" if offset == 7 else "continuous",
            occurrences=(Occurrence(now.date() - timedelta(days=offset)),),
            place=Place("Am Markte", "30159", "Hannover"),
        )
        for offset in (0, 1, 7, 8)
    ]
    prior_time = now - timedelta(days=9)
    programme = [
        Event(
            title=f"Programme for {definition.slug}",
            date=datetime.combine(
                definition.end_date, datetime.min.time(), tzinfo=BERLIN_TZ
            ),
            venue="Marktplatz",
            url=definition.source_url,
            category="radar",
            metadata={"occasion_id": definition.id},
        )
        for definition in definitions
    ]
    export_web_json(
        [],
        programme,
        root,
        45,
        now.year,
        generated_at=prior_time,
        occasion_definitions=definitions,
    )
    files = {
        f"web/output/{path.relative_to(root).as_posix()}": path.read_bytes()
        for path in [
            root / "web_events.json",
            *sorted((root / "occasions").glob("*.json")),
        ]
    }
    serve_github_publication(local_site, files)
    current_definitions = definitions if rediscovered else []
    export_web_json(
        [],
        [],
        root,
        45,
        now.year,
        generated_at=now,
        occasion_definitions=current_definitions,
    )
    with httpx.Client(base_url=local_site.url) as client:
        carry_forward_occasions(
            root,
            definitions=current_definitions,
            now=now,
            client=client,
            repo="test/events",
        )
    manifest = json.loads((root / "web_events.json").read_text())
    assert {item["slug"] for item in manifest["occasions"]} == {
        "retained-0",
        "retained-1",
        "retained-7",
    }
    for offset in (1, 7):
        programme = json.loads((root / f"occasions/retained-{offset}.json").read_text())
        original = json.loads(files[f"web/output/occasions/retained-{offset}.json"])
        assert programme["meta"] == (
            {"updatedAt": now.strftime("%a %d %b %H:%M")}
            if rediscovered
            else original["meta"]
        )
        assert programme["occasion"] == {**original["occasion"], "status": "ended"}
        assert programme["programme"] == original["programme"]

    # A retained publication is itself valid input to the next production run.
    serve_github_publication(
        local_site,
        {
            f"web/output/{path.relative_to(root).as_posix()}": path.read_bytes()
            for path in [
                root / "web_events.json",
                *sorted((root / "occasions").glob("*.json")),
            ]
        },
    )
    export_web_json([], [], root, 45, now.year, generated_at=now)
    with httpx.Client(base_url=local_site.url) as client:
        carry_forward_occasions(
            root, definitions=[], now=now, client=client, repo="test/events"
        )
    assert json.loads((root / "web_events.json").read_text()) == manifest

    # Even a stale publication must not rebuild a page beyond the seven dates.
    expired = json.loads(files["web/output/occasions/retained-8.json"])
    (root / "occasions/retained-8.json").write_text(json.dumps(expired))
    manifest["occasions"].append(expired["occasion"])
    (root / "web_events.json").write_text(json.dumps(manifest))
    dist = tmp_path / "dist"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("WEB_DATA_")
    }
    build = subprocess.run(
        [BUN, str(ASTRO), "build", "--root", str(WEB), "--outDir", str(dist)],
        cwd=tmp_path,
        env={
            **env,
            "SITE": "https://boringhannover.de",
            "WEB_DATA_ROOT": str(root),
            "WEB_DATA_MODE": "production",
        },
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    sitemap = (dist / "sitemap.xml").read_text()
    home = (dist / "index.html").read_text()
    index = (dist / "special/index.html").read_text()
    assert "/special/retained-0/" in sitemap
    active = BeautifulSoup(
        (dist / "special/retained-0/index.html").read_text(), "html.parser"
    )
    assert active.select_one('meta[name="robots"]') is None
    for offset in (1, 7, 8):
        url = f"/special/retained-{offset}/"
        assert url not in sitemap and url not in home and url not in index
    assert not (dist / "special/retained-8/index.html").exists()
    for offset in (1, 7):
        page = BeautifulSoup(
            (dist / f"special/retained-{offset}/index.html").read_text(), "html.parser"
        )
        assert page.select_one('meta[name="robots"]')["content"] == "noindex, follow"
        assert "Ended" in page.get_text()
        assert "Am Markte" in page.get_text()
        assert f"Programme for retained-{offset}" in page.get_text()
        assert page.select_one("[data-occasion-actions]") is None
        assert page.select_one('a[href="/special/"]') is not None
        assert page.select_one('[data-umami-event="occasion-source-open"]') is not None
        assert page.select_one(f'a[href="/special/retained-{8 - offset}/"]') is None


def test_christmas_facts_survive_carry_forward_and_reach_the_detail_sheet(
    local_site: LocalSite, tmp_path: Path
) -> None:
    now = datetime(2026, 11, 6, 12, tzinfo=BERLIN_TZ)
    events = fetch_all_events(
        sources={"christmas": serve_christmas_calendar(local_site)}, now=now
    )
    root = tmp_path / "output"
    root.mkdir()
    export_web_json(
        [],
        [],
        root,
        45,
        2026,
        generated_at=now,
        occasion_definitions=events["city_occasions"],
    )
    original = json.loads((root / "web_events.json").read_text())
    serve_github_publication(
        local_site,
        {
            f"web/output/{path.relative_to(root).as_posix()}": path.read_bytes()
            for path in [
                root / "web_events.json",
                *sorted((root / "occasions").glob("*.json")),
            ]
        },
    )
    export_web_json([], [], root, 45, 2026, generated_at=now)
    with httpx.Client(base_url=local_site.url) as client:
        carry_forward_occasions(
            root, definitions=[], now=now, client=client, repo="test/events"
        )
    assert {
        item["slug"]: item
        for item in json.loads((root / "web_events.json").read_text())["occasions"]
    } == {item["slug"]: item for item in original["occasions"]}
    dist = tmp_path / "dist"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("WEB_DATA_", "PUBLIC_UMAMI_"))
    }
    build = subprocess.run(
        [BUN, str(ASTRO), "build", "--root", str(WEB), "--outDir", str(dist)],
        cwd=tmp_path,
        # Captured source dates deliberately stay fixed, even after this season.
        env={
            **env,
            "WEB_DATA_ROOT": str(root),
            "WEB_DATA_MODE": "fixture",
            "PUBLIC_UMAMI_WEBSITE_ID": "00000000-0000-4000-8000-000000000077",
        },
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    zoo_html = (dist / "special/magische-lichterwelten-im-zoo/index.html").read_text()
    zoo = BeautifulSoup(zoo_html, "html.parser")
    text = zoo.get_text(" ", strip=True)
    assert "Adults:" in text and "from €23.80" in text
    assert "Children aged 5\u201317:" in text and "from €14.80" in text
    assert "Free entry" not in text
    # Sparse opening dates must not become a single continuous schema.org Event.
    assert '"@type":"Event"' not in zoo_html
    assert len(zoo.select("[data-occurrence-date]")) == 18
    assert zoo.select_one("details[data-schedule-more] > summary") is not None
    dates = {
        item["data-occurrence-date"] for item in zoo.select("[data-occurrence-date]")
    }
    assert "2026-11-23" not in dates and "2026-12-06" in dates
    index = (dist / "special/index.html").read_text()
    for record in original["occasions"]:
        assert f"/special/{record['slug']}/" in index

    # Numberless official streets/squares must reach both the visible facts
    # and Event JSON-LD after export and pinned-publication carry-forward.
    for slug, street, postal in [
        ("weihnachtsmarkt-hannover", "Am Markte", "30159"),
        ("weihnachtsmarkt-lister-meile", "Lister Meile", "30161"),
        ("adventsmarkt-in-dohren", "Fiedelerplatz", "30519"),
        ("weihnachtsdorf-am-hauptbahnhof", "Ernst-August-Platz", "30159"),
    ]:
        page = BeautifulSoup(
            (dist / "special" / slug / "index.html").read_text(), "html.parser"
        )
        assert f"{street} {postal} Hannover" in page.get_text(" ", strip=True)
        nodes = [
            json.loads(script.string)
            for script in page.select('script[type="application/ld+json"]')
        ]
        events = [node for node in nodes if node.get("@type") == "Event"]
        if slug == "weihnachtsdorf-am-hauptbahnhof":
            # Its excluded dates still prohibit a continuous-season Event.
            assert not events
        else:
            assert len(events) == 1
            assert events[0]["location"]["address"] == {
                "@type": "PostalAddress",
                "streetAddress": street,
                "postalCode": postal,
                "addressLocality": "Hannover",
                "addressCountry": "DE",
            }


def test_month_ahead_occasions_reach_export_carry_forward_and_built_site(
    local_site: LocalSite, tmp_path: Path
) -> None:
    now = datetime.now(BERLIN_TZ)

    def day(offset: int) -> date:
        return now.date() + timedelta(days=offset)

    listing_path = "/Veranstaltungskalender/Feste-Festivals"
    cards = []
    for offset in (15, 30, 31):
        slug = f"month-fest-{offset}"
        detail_path = f"{listing_path}/{slug}"
        cards.append(
            '<article class="interesting-single line-view-content">'
            f'<h2 class="interesting-single__title">{slug}</h2>'
            f'<span class="date__duration">{day(offset):%d.%m.%Y}</span>'
            '<a class="content__read-more" '
            f'href="https://www.hannover.de{detail_path}">mehr</a></article>'
        )
        local_site.pages[detail_path] = (
            200,
            '<div class="details"><div class="detail-row">'
            '<div class="detail-cell"><p>Termine</p></div>'
            '<div class="detail-cell">'
            f"<p>{day(offset):%d.%m.%Y} ab 14:00 bis 18:00 Uhr</p></div></div>"
            '<div class="detail-row"><div class="detail-cell"><p>Ort</p></div>'
            '<div class="detail-cell"><p>Parkbühne</p>'
            "<p>Ferdinand-Wilhelm-Fricke-Weg 8</p><p>30169 Hannover</p>"
            "</div></div></div>",
        )
    local_site.pages[listing_path] = (200, "".join(cards))

    class LocalCalendar(HannoverFestivalCalendarSource):
        CALENDAR_URL = f"{local_site.url}{listing_path}"

    events = fetch_all_events(sources={"calendar": LocalCalendar}, now=now)
    data_root = tmp_path / "output"
    data_root.mkdir()
    iso_year, iso_week, _ = now.isocalendar()
    export_web_json(
        [],
        [],
        data_root,
        iso_week,
        iso_year,
        occasion_definitions=events["city_occasions"],
        generated_at=now,
    )
    manifest = json.loads((data_root / "web_events.json").read_text())
    assert [item["slug"] for item in manifest["occasions"]] == [
        "month-fest-15",
        "month-fest-30",
    ]
    assert manifest["occasions"][1]["occurrences"] == [
        {"date": str(day(30)), "startTime": "14:00", "endTime": "18:00"}
    ]
    assert f"{listing_path}/month-fest-31" not in local_site.requests
    serve_github_publication(
        local_site,
        {
            f"web/output/{path.relative_to(data_root).as_posix()}": path.read_bytes()
            for path in [
                data_root / "web_events.json",
                *sorted((data_root / "occasions").glob("*.json")),
            ]
        },
    )
    # Both occasions are omitted on the next scrape, but still inside 30 days.
    export_web_json([], [], data_root, iso_week, iso_year, generated_at=now)
    with httpx.Client(base_url=local_site.url) as client:
        carry_forward_occasions(
            data_root, definitions=[], now=now, client=client, repo="test/events"
        )
    retained = json.loads((data_root / "web_events.json").read_text())
    assert retained["occasions"] == manifest["occasions"]

    dist = tmp_path / "dist"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("WEB_DATA_")
    }
    build = subprocess.run(
        [BUN, str(ASTRO), "build", "--root", str(WEB), "--outDir", str(dist)],
        cwd=tmp_path,
        env={**env, "WEB_DATA_ROOT": str(data_root), "WEB_DATA_MODE": "production"},
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    index = (dist / "special/index.html").read_text()
    for offset in (15, 30):
        assert f'href="/special/month-fest-{offset}/"' in index
        detail = (dist / f"special/month-fest-{offset}/index.html").read_text()
        assert "14:00\u201318:00" in detail
    assert "month-fest-31" not in index


def test_scraped_events_reach_the_built_site(
    local_site: LocalSite, tmp_path: Path
) -> None:
    now = datetime.now(BERLIN_TZ)
    tomorrow = now + timedelta(days=1)
    in_three_days = now + timedelta(days=3)

    local_site.pages["/astor"] = (
        200,
        json.dumps(
            {
                "genres": [],
                "movies": [{"id": 1, "name": "Pipeline Movie", "year": 2026}],
                "performances": [
                    {
                        "movieId": 1,
                        "begin": tomorrow.strftime("%Y-%m-%dT19:30:00"),
                        "language": "Sprache: Englisch",
                    }
                ],
            }
        ),
    )
    local_site.pages["/kulturpalast.ics"] = (
        200,
        "\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Test//EN",
                "BEGIN:VEVENT",
                f"DTSTART;TZID=Europe/Berlin:{in_three_days:%Y%m%d}T200000",
                "SUMMARY:Pipeline Concert",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        ),
    )

    class LocalAstor(AstorSource):
        API_URL = f"{local_site.url}/astor"

    class LocalKulturpalast(KulturpalastLindenSource):
        ICAL_URL = f"{local_site.url}/kulturpalast.ics"
        # A source-owned occasion goes through the real discover_occasions().
        occasion = OccasionDefinition(
            id="e2e:pipeline-fest",
            slug="pipeline-fest",
            name="Pipeline Fest",
            kind="festival",
            start_date=now.date(),
            end_date=in_three_days.date(),
            location="Kulturpalast Linden",
            source_url="https://www.hannover.de/Veranstaltungskalender/Pipeline-Fest",
            description="Ein Fest, das nur in diesem Test stattfindet.",
        )

    events = fetch_all_events(
        sources={"astor": LocalAstor, "kulturpalast": LocalKulturpalast}
    )
    data_root = tmp_path / "output"
    data_root.mkdir()
    iso_year, iso_week, _ = now.isocalendar()
    export_web_json(
        events["movies_this_week"],
        events["big_events_radar"],
        data_root,
        iso_week,
        iso_year,
        occasion_definitions=events["city_occasions"],
    )

    serve_github_publication(
        local_site,
        {
            f"web/output/{path.relative_to(data_root).as_posix()}": path.read_bytes()
            for path in [
                data_root / "web_events.json",
                *sorted((data_root / "occasions").glob("*.json")),
            ]
        },
    )
    prior = json.loads((data_root / "occasions/pipeline-fest.json").read_text())
    export_web_json(
        events["movies_this_week"],
        events["big_events_radar"],
        data_root,
        iso_week,
        iso_year,
        occasion_definitions=[],
        generated_at=now,
    )
    assert not (data_root / "occasions/pipeline-fest.json").exists()
    with httpx.Client(base_url=local_site.url) as client:
        carry_forward_occasions(
            data_root, definitions=[], now=now, client=client, repo="test/events"
        )
    retained = json.loads((data_root / "occasions/pipeline-fest.json").read_text())
    assert retained["meta"] == prior["meta"]

    dist = tmp_path / "dist"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("WEB_DATA_")
    }
    build = subprocess.run(
        [BUN, str(ASTRO), "build", "--root", str(WEB), "--outDir", str(dist)],
        cwd=tmp_path,
        env={**env, "WEB_DATA_ROOT": str(data_root), "WEB_DATA_MODE": "production"},
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr

    homepage = (dist / "index.html").read_text(encoding="utf-8")
    assert "Pipeline Movie" in homepage
    assert "Pipeline Concert" in homepage
    assert "Pipeline Fest" in homepage
    occasion_page = dist / "special" / "pipeline-fest" / "index.html"
    html = occasion_page.read_text(encoding="utf-8")
    assert "Pipeline Fest" in html
    assert f"checked {prior['meta']['updatedAt']}" in html
