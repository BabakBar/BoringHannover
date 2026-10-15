"""A production run that cannot publish or back up must not report success.

The site serves whatever was last committed, so a run that scrapes but fails
to sync leaves stale data up. Reporting success there hides the outage from
the scheduler, which is how the 28 Aug data stayed live for two run cycles.
A run whose sources make its output unsafe must not replace the site at all.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from boringhannover import main
from boringhannover.aggregator import fetch_all_events
from boringhannover.constants import BERLIN_TZ
from boringhannover.github_sync import (
    WEB_EVENTS_REPO_PATH,
    WEB_OCCASIONS_REPO_DIR,
    _collect_web_sync_paths,
    _normalize_events_json,
)
from boringhannover.models import Event
from boringhannover.source_outcomes import SourceOutcome
from boringhannover.sources.base import BaseSource
from boringhannover.sources.festivals.hannover_calendar import (
    HannoverFestivalCalendarSource,
)


if TYPE_CHECKING:
    from collections.abc import Callable

    from conftest import LocalSite


FIXTURES = Path(__file__).parent / "fixtures"
LISTING_PATH = "/Veranstaltungskalender/Feste-Festivals"
LOAD_MORE_PATH = "/api/v1/view/533295/10/10/line"
EMPTY_LISTING = (
    '<html><body><h1 class="content-detail__title">Feste &amp; Festivals</h1>'
    "</body></html>"
)
FETCHED = SourceOutcome("venue", "fetch", "success", 1, "unknown")
PARTIAL = SourceOutcome(
    "festivals", "discover_occasions", "partial", 2, "incomplete", "page 2 failed"
)


@pytest.mark.parametrize(
    (
        "outcomes",
        "local",
        "sync_configured",
        "sync_ok",
        "backup_ok",
        "succeeded",
        "calls",
    ),
    [
        pytest.param(
            [FETCHED], False, True, True, True, True, ["backup", "sync"], id="ok"
        ),
        pytest.param(
            [FETCHED],
            False,
            True,
            False,
            True,
            False,
            ["backup", "sync"],
            id="sync-fails",
        ),
        pytest.param(
            [FETCHED],
            False,
            False,
            True,
            True,
            False,
            ["backup"],
            id="sync-not-configured",
        ),
        # Fresh data still goes out; the gap in the history fails the run.
        pytest.param(
            [FETCHED],
            False,
            True,
            True,
            False,
            False,
            ["backup", "sync"],
            id="backup-fails",
        ),
        pytest.param(
            [FETCHED], True, False, False, False, True, [], id="local-skips-both"
        ),
        # Unsafe output is neither backed up nor published.
        pytest.param(
            [FETCHED, PARTIAL], False, True, True, True, False, [], id="unsafe"
        ),
        # Without outcomes there is no evidence the output is safe.
        pytest.param([], False, True, True, True, False, [], id="no-outcomes"),
        # A local run publishes nothing, so it only warns.
        pytest.param(
            [FETCHED, PARTIAL], True, True, True, True, True, [], id="local-unsafe"
        ),
    ],
)
def test_run_reports_publication_and_backup_failures(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[SourceOutcome],
    local: bool,
    sync_configured: bool,
    sync_ok: bool,
    backup_ok: bool,
    succeeded: bool,
    calls: list[str],
) -> None:
    recorded: list[str] = []

    def backup(output_dir: str) -> bool:
        recorded.append("backup")
        assert output_dir == "output"
        return backup_ok

    def sync(output_dir: str) -> bool:
        recorded.append("sync")
        assert output_dir == "output"
        return sync_ok

    monkeypatch.setattr(
        main,
        "fetch_all_events",
        lambda **_: {
            "movies_this_week": [],
            "big_events_radar": [],
            "source_outcomes": outcomes,
        },
    )
    monkeypatch.setattr(main, "export_run", lambda _events, **_: None)
    monkeypatch.setattr(main, "backup_run", backup)
    monkeypatch.setattr(main, "should_sync", lambda: sync_configured)
    monkeypatch.setattr(main, "sync_web_data_to_github", sync)

    assert main.run(local=local) is succeeded
    assert recorded == calls


def _serve_empty_listing(site: LocalSite) -> None:
    site.pages[LISTING_PATH] = (200, EMPTY_LISTING)


def _serve_failed_listing(site: LocalSite) -> None:
    site.pages[LISTING_PATH] = (500, "")


def _serve_listing_with_failed_page(site: LocalSite) -> None:
    listing = (FIXTURES / "hannover_festivals_listing.html").read_text("utf-8")
    site.pages[LISTING_PATH] = (200, listing)
    site.pages[LOAD_MORE_PATH] = (502, "")


@pytest.mark.parametrize(
    ("serve", "venue_fails", "published", "occasions", "reason"),
    [
        pytest.param(
            _serve_empty_listing, False, True, [], None, id="empty-season-publishes"
        ),
        pytest.param(
            _serve_failed_listing,
            False,
            False,
            [],
            "Not publishing: incomplete occasion discovery: festivals "
            "discover_occasions: failed, 0 usable, completion incomplete "
            "(HTTPStatusError: Server error '500 Internal Server Error'",
            id="failed-discovery-refused",
        ),
        # The rows read are exported for diagnosis, but some rows are not
        # proof that publishing is safe.
        pytest.param(
            _serve_listing_with_failed_page,
            False,
            False,
            [
                "hannover-festivals:oktoberfest-2026",
                "hannover-festivals:hannover-wies-27n",
            ],
            "Not publishing: incomplete occasion discovery: festivals "
            "discover_occasions: partial",
            id="partial-discovery-refused",
        ),
        pytest.param(
            _serve_empty_listing,
            True,
            False,
            [],
            "Not publishing: no source fetched any events: venue fetch: failed",
            id="total-fetch-failure-refused",
        ),
    ],
)
def test_run_publishes_only_safe_source_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    local_site: LocalSite,
    tmp_path: Path,
    serve: Callable[[LocalSite], None],
    venue_fails: bool,
    published: bool,
    occasions: list[str],
    reason: str | None,
) -> None:
    """Real aggregation of localhost sources decides whether main.run publishes."""
    serve(local_site)
    tomorrow = datetime.now(BERLIN_TZ) + timedelta(days=1)

    class Venue(BaseSource):
        source_name = "Venue"
        source_type = "concert"

        def fetch(self) -> list[Event]:
            if venue_fails:
                msg = "venue unreachable"
                raise ConnectionError(msg)
            return [
                Event(
                    title="Concert",
                    date=tomorrow,
                    venue="Venue",
                    url="https://example.com/concert",
                    category="radar",
                )
            ]

    # Detail pages are requested from this origin too; unserved ones are 404.
    class Festivals(HannoverFestivalCalendarSource):
        CALENDAR_URL = f"{local_site.url}{LISTING_PATH}"

    recorded: list[str] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        main,
        "fetch_all_events",
        lambda **kwargs: fetch_all_events(
            sources={"venue": Venue, "festivals": Festivals}, **kwargs
        ),
    )
    monkeypatch.setattr(main, "backup_run", lambda _: recorded.append("backup") or True)
    monkeypatch.setattr(main, "should_sync", lambda: True)
    monkeypatch.setattr(
        main, "sync_web_data_to_github", lambda _: recorded.append("sync") or True
    )

    assert main.run() is published
    assert recorded == (["backup", "sync"] if published else [])
    if reason is not None:
        assert reason in caplog.text
    # Every run writes its local output; the archive keeps each occasion read.
    assert (tmp_path / "output" / "web_events.json").exists()
    (archive,) = (tmp_path / "output" / "archive").glob("*.json")
    discovered = [
        occasion["id"]
        for occasion in json.loads(archive.read_text("utf-8"))["occasions"]
        if occasion["id"].startswith("hannover-festivals:")
    ]
    assert discovered == occasions


def test_sync_writes_occasion_programmes_before_the_manifest(tmp_path) -> None:
    """The manifest lands last, so a half-finished sync never points at
    programmes that are not there yet."""
    occasions = tmp_path / "occasions"
    occasions.mkdir()
    (occasions / "z-event.json").write_text("{}", encoding="utf-8")
    (occasions / "a-event.json").write_text("{}", encoding="utf-8")
    (tmp_path / "web_events.json").write_text("{}", encoding="utf-8")

    paths = _collect_web_sync_paths(tmp_path)

    assert [repo_path for _, repo_path in paths] == [
        f"{WEB_OCCASIONS_REPO_DIR}/a-event.json",
        f"{WEB_OCCASIONS_REPO_DIR}/z-event.json",
        WEB_EVENTS_REPO_PATH,
    ]


def test_sync_change_detection_ignores_only_the_timestamps() -> None:
    """Otherwise every scrape commits, redeploys, and moves lastmod for nothing."""

    def normalized(meta: dict, **content: object) -> bytes:
        return _normalize_events_json(json.dumps({"meta": meta, **content}).encode())

    base = {"week": 31, "year": 2026}
    earlier = {
        **base,
        "updatedAt": "Sun 26 Jul 16:08",
        "updatedAtISO": "2026-07-26T16:08:00+02:00",
    }
    later = {
        **base,
        "updatedAt": "Fri 14 Aug 09:01",
        "updatedAtISO": "2026-08-14T09:01:49+02:00",
    }

    assert normalized(earlier, movies=[]) == normalized(later, movies=[])
    assert normalized(earlier, movies=[]) != normalized(earlier, movies=["new"])
