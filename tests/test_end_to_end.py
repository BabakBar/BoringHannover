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

from boringhannover.aggregator import fetch_all_events
from boringhannover.constants import BERLIN_TZ
from boringhannover.exporters import export_web_json
from boringhannover.github_sync import carry_forward_occasions
from boringhannover.occasions import OccasionDefinition
from boringhannover.sources.cinema.astor import AstorSource
from boringhannover.sources.concerts.kulturpalast_linden import (
    KulturpalastLindenSource,
)
from boringhannover.sources.festivals.hannover_calendar import (
    HannoverFestivalCalendarSource,
)
from conftest import serve_github_publication


if TYPE_CHECKING:
    from conftest import LocalSite


WEB = Path(__file__).parents[1] / "web"
ASTRO = WEB / "node_modules" / "astro" / "bin" / "astro.mjs"
BUN = shutil.which("bun")

pytestmark = pytest.mark.skipif(
    BUN is None or not ASTRO.exists(),
    reason="needs bun and web/node_modules (run `bun install` in web/)",
)


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
