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
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from boringhannover.aggregator import fetch_all_events
from boringhannover.constants import BERLIN_TZ
from boringhannover.exporters import export_web_json
from boringhannover.occasions import OccasionDefinition
from boringhannover.sources.cinema.astor import AstorSource
from boringhannover.sources.concerts.kulturpalast_linden import (
    KulturpalastLindenSource,
)


if TYPE_CHECKING:
    from conftest import LocalSite


WEB = Path(__file__).parents[1] / "web"
ASTRO = WEB / "node_modules" / "astro" / "bin" / "astro.mjs"
BUN = shutil.which("bun")

pytestmark = pytest.mark.skipif(
    BUN is None or not ASTRO.exists(),
    reason="needs bun and web/node_modules (run `bun install` in web/)",
)


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
    assert "Pipeline Fest" in occasion_page.read_text(encoding="utf-8")
