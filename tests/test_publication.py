"""A production run that cannot publish or back up must not report success.

The site serves whatever was last committed, so a run that scrapes but fails
to sync leaves stale data up. Reporting success there hides the outage from
the scheduler, which is how the 28 Aug data stayed live for two run cycles.
A run whose sources make its output unsafe must not replace the site at all.
"""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from bs4 import BeautifulSoup

from boringhannover import main
from boringhannover.aggregator import fetch_all_events
from boringhannover.constants import BERLIN_TZ
from boringhannover.github_sync import (
    WEB_EVENTS_REPO_PATH,
    WEB_OCCASIONS_REPO_DIR,
    _collect_web_sync_paths,
    _normalize_events_json,
    _sync_file,
)
from boringhannover.models import Event
from boringhannover.occasions import OccasionDefinition, Occurrence
from boringhannover.output import export_run
from boringhannover.source_outcomes import SourceOutcome
from boringhannover.sources.base import BaseSource
from boringhannover.sources.festivals.hannover_calendar import (
    HannoverFestivalCalendarSource,
)
from conftest import serve_github_publication


if TYPE_CHECKING:
    from collections.abc import Callable

    from conftest import LocalSite


FIXTURES = Path(__file__).parent / "fixtures"
LISTING_PATH = "/Veranstaltungskalender/Feste-Festivals"
LOAD_MORE_PATH = "/api/v1/view/533295/10/10/line"
FETCHED = SourceOutcome("venue", "fetch", "success", 1, "unknown")
PARTIAL = SourceOutcome(
    "festivals", "discover_occasions", "partial", 2, "incomplete", "page 2 failed"
)
CONCERT = Event(
    title="Concert",
    date=datetime(2026, 10, 16, 20, 0, tzinfo=BERLIN_TZ),
    venue="Venue",
    url="https://example.com/concert",
    category="radar",
)
SAFE = {
    "movies_this_week": [],
    "big_events_radar": [CONCERT],
    "source_outcomes": [FETCHED],
}
UNSAFE = {**SAFE, "source_outcomes": [FETCHED, PARTIAL]}


@pytest.mark.parametrize(
    (
        "events_data",
        "local",
        "sync_configured",
        "sync_ok",
        "backup_ok",
        "succeeded",
        "calls",
    ),
    [
        pytest.param(SAFE, False, True, True, True, True, ["backup", "sync"], id="ok"),
        pytest.param(
            SAFE,
            False,
            True,
            False,
            True,
            False,
            ["backup", "sync"],
            id="sync-fails",
        ),
        pytest.param(
            SAFE,
            False,
            False,
            True,
            True,
            False,
            [],
            id="sync-not-configured",
        ),
        # Fresh data still goes out; the gap in the history fails the run.
        pytest.param(
            SAFE,
            False,
            True,
            True,
            False,
            False,
            ["backup", "sync"],
            id="backup-fails",
        ),
        pytest.param(SAFE, True, False, False, False, True, [], id="local-skips-both"),
        # Unsafe output is neither backed up nor published.
        pytest.param(UNSAFE, False, True, True, True, False, [], id="unsafe"),
        # Sources answered, but nothing would be published.
        pytest.param(
            {**SAFE, "big_events_radar": []},
            False,
            True,
            True,
            True,
            False,
            [],
            id="empty-replacement",
        ),
        # A local run publishes nothing, so it only warns.
        pytest.param(UNSAFE, True, True, True, True, True, [], id="local-unsafe"),
    ],
)
def test_run_reports_publication_and_backup_failures(
    monkeypatch: pytest.MonkeyPatch,
    events_data: dict[str, object],
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
        lambda **_: events_data,
    )
    monkeypatch.setattr(main, "export_run", lambda _events, **_: None)
    monkeypatch.setattr(main, "carry_forward_occasions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "backup_run", backup)
    monkeypatch.setattr(main, "should_sync", lambda: sync_configured)
    monkeypatch.setattr(main, "sync_web_data_to_github", sync)

    assert main.run(local=local) is succeeded
    assert recorded == calls


def _serve_empty_listing(site: LocalSite) -> None:
    site.pages[LISTING_PATH] = (200, _region_only_listing())


def _serve_failed_listing(site: LocalSite) -> None:
    site.pages[LISTING_PATH] = (500, "")


def _serve_listing_with_failed_page(site: LocalSite) -> None:
    listing = (FIXTURES / "hannover_festivals_listing.html").read_text("utf-8")
    site.pages[LISTING_PATH] = (200, listing)
    site.pages[LOAD_MORE_PATH] = (502, "")


def _region_only_listing() -> str:
    """The captured listing with only its Langenhagen card: read, then filtered."""
    soup = BeautifulSoup(
        (FIXTURES / "hannover_festivals.html").read_text("utf-8"), "html.parser"
    )
    for card in soup.select("article"):
        if "Langenhagen" not in card.get_text():
            card.decompose()
    return str(soup)


@pytest.mark.parametrize(
    ("serve", "venue", "published", "occasions", "reason"),
    [
        pytest.param(
            _serve_empty_listing, "ok", True, [], None, id="empty-discovery-publishes"
        ),
        pytest.param(
            _serve_failed_listing,
            "ok",
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
            "ok",
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
            "fails",
            False,
            [],
            "Not publishing: no events to publish: venue fetch: failed",
            id="total-fetch-failure-refused",
        ),
        # Rows a source returned are not publishable if all have ended.
        pytest.param(
            _serve_empty_listing,
            "stale",
            False,
            [],
            "Not publishing: no events to publish",
            id="only-expired-rows-refused",
        ),
    ],
)
def test_run_publishes_only_safe_source_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    local_site: LocalSite,
    tmp_path: Path,
    serve: Callable[[LocalSite], None],
    venue: str,
    published: bool,
    occasions: list[str],
    reason: str | None,
) -> None:
    """Real aggregation of localhost sources decides whether main.run publishes."""
    serve(local_site)
    when = datetime.now(BERLIN_TZ) + timedelta(days=-30 if venue == "stale" else 1)

    class Venue(BaseSource):
        source_name = "Venue"
        source_type = "concert"

        def fetch(self) -> list[Event]:
            if venue == "fails":
                msg = "venue unreachable"
                raise ConnectionError(msg)
            return [
                Event(
                    title="Concert",
                    date=when,
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
    monkeypatch.setattr(main, "carry_forward_occasions", lambda *_args, **_kwargs: None)
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


@pytest.mark.parametrize(
    "programme_source", ["absent", "explicit-id", "title", "sticky-cancellation"]
)
def test_run_carries_known_publication_through_complete_discovery_omission(
    programme_source: str,
    monkeypatch: pytest.MonkeyPatch,
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    """Real exports, GitHub HTTP reads and PUTs go through main.run twice."""
    from boringhannover import github_sync

    now = datetime.now(BERLIN_TZ)
    tomorrow = now + timedelta(days=1)
    occasion = OccasionDefinition(
        id="test:known",
        slug="known",
        name="Known festival",
        kind="festival",
        start_date=now.date(),
        end_date=(now + timedelta(days=5)).date(),
        location="Hannover",
        source_url="https://example.com/known",
        description="A known festival.",
        schedule_confidence="continuous",
    )
    event = Event(
        title="Fresh concert",
        date=tomorrow,
        venue="Venue",
        url="https://example.com/fresh",
        category="radar",
    )
    programme = Event(
        title="Known festival first show",
        date=tomorrow,
        venue="Venue",
        url="https://example.com/programme",
        category="radar",
        metadata={} if programme_source == "title" else {"occasion_id": occasion.id},
    )
    definitions = [occasion]
    if programme_source == "sticky-cancellation":
        programme.metadata["status"] = "cancelled"
    events = [event, programme]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        main,
        "fetch_all_events",
        lambda **_: {
            "movies_this_week": [],
            "big_events_radar": events,
            "city_occasions": definitions,
            "source_outcomes": [
                FETCHED,
                SourceOutcome(
                    "festivals",
                    "discover_occasions",
                    "success" if definitions else "empty",
                    len(definitions),
                    "complete",
                ),
            ],
        },
    )
    monkeypatch.setattr(main, "should_sync", lambda: True)
    backed_up = []
    monkeypatch.setattr(main, "backup_run", lambda _: backed_up.append(True) or True)
    serve_github_publication(local_site, {})
    with httpx.Client(base_url=local_site.url) as client:

        def reconcile(output_dir: str, **kwargs: object) -> None:
            github_sync.carry_forward_occasions(
                output_dir, client=client, repo="test/events", **kwargs
            )

        monkeypatch.setattr(main, "carry_forward_occasions", reconcile, raising=False)
        monkeypatch.setattr(
            main,
            "sync_web_data_to_github",
            lambda output_dir: all(
                _sync_file(client, "test/events", path, remote)
                for path, remote in _collect_web_sync_paths(output_dir)
            ),
        )
        assert main.run()
        published = {
            path.removeprefix("/repos/test/events/contents/"): base64.b64decode(
                str(payload["content"])
            )
            for path, payload in local_site.puts
        }
        prior_programme = json.loads(published["web/output/occasions/known.json"])
        published["web/output/occasions/orphan.json"] = b"{not inventory"
        serve_github_publication(local_site, published)
        definitions.clear()
        if programme_source == "absent":
            events.remove(programme)
        else:
            events.append(
                replace(
                    programme,
                    title="Known festival new show",
                    url="https://example.com/new-programme",
                )
            )
            if programme_source == "sticky-cancellation":
                events[1] = replace(programme, metadata={"occasion_id": occasion.id})
        event = Event(
            title="Newly discovered concert",
            date=tomorrow,
            venue="Venue",
            url="https://example.com/new",
            category="radar",
        )
        events[0] = event
        local_site.puts.clear()
        local_site.requests.clear()
        assert main.run()

    manifest = json.loads((tmp_path / "output/web_events.json").read_text())
    assert [item["id"] for item in manifest["occasions"]] == [occasion.id]
    retained = json.loads((tmp_path / "output/occasions/known.json").read_text())
    assert [item["title"] for item in manifest["concerts"]] == [event.title]
    assert retained["meta"] == prior_programme["meta"]
    if programme_source == "absent":
        assert retained == prior_programme
    else:
        assert {item["title"] for item in retained["programme"]} == {
            programme.title,
            "Known festival new show",
        }
        assert len(retained["programme"]) == 2
        assert retained["occasion"]["programmeCount"] == 2
        if programme_source == "sticky-cancellation":
            assert (
                next(
                    item
                    for item in retained["programme"]
                    if item["title"] == programme.title
                )["status"]
                == "cancelled"
            )
    assert manifest["occasions"][0] == retained["occasion"]
    assert manifest["concerts"][0]["title"] == event.title
    assert backed_up == [True, True]
    assert local_site.puts[-1][0].endswith("web/output/web_events.json")
    prior_reads = [path for path in local_site.requests if "?ref=" in path]
    assert len(prior_reads) == 2
    assert all(path.endswith(f"?ref={'a' * 40}") for path in prior_reads)


@pytest.fixture
def known_publication(
    tmp_path: Path,
) -> tuple[OccasionDefinition, Event, dict[str, bytes]]:
    now = datetime.now(BERLIN_TZ)
    occasion = OccasionDefinition(
        id="test:known",
        slug="known",
        name="Known festival",
        kind="festival",
        start_date=(now - timedelta(days=2)).date(),
        end_date=(now + timedelta(days=5)).date(),
        location="Hannover",
        source_url="https://example.com/known",
        description="A known festival.",
        schedule_confidence="continuous",
        source_status="scheduled",
    )
    event = Event(
        title="Fresh concert",
        date=now + timedelta(days=1),
        venue="Venue",
        url="https://example.com/fresh",
        category="radar",
    )
    root = tmp_path / "prior"
    export_run(
        {
            "movies_this_week": [],
            "big_events_radar": [event],
            "city_occasions": [occasion],
            "source_outcomes": [FETCHED],
        },
        root,
        now=now - timedelta(days=1),
    )
    return (
        occasion,
        event,
        {
            f"web/output/{path.relative_to(root).as_posix()}": path.read_bytes()
            for path in [root / "web_events.json", root / "occasions/known.json"]
        },
    )


def test_carried_programmes_use_the_export_year_at_an_iso_year_boundary(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    from boringhannover.github_sync import carry_forward_occasions

    now = datetime(2027, 1, 1, 12, tzinfo=BERLIN_TZ)
    definition = OccasionDefinition(
        id="test:year",
        slug="year",
        name="Year festival",
        kind="festival",
        start_date=(now - timedelta(days=1)).date(),
        end_date=(now + timedelta(days=2)).date(),
        location="Hannover",
        source_url="https://example.com/year",
        description="Year fixture.",
        schedule_confidence="continuous",
    )
    event = Event(
        title="Year festival show",
        date=now + timedelta(days=1),
        venue="Venue",
        url="https://example.com/show",
        category="radar",
        metadata={"occasion_id": definition.id},
    )
    data = {
        "movies_this_week": [],
        "big_events_radar": [event],
        "city_occasions": [definition],
        "source_outcomes": [FETCHED],
    }
    root = tmp_path / "output"
    export_run(data, root, now=now - timedelta(days=1))
    serve_github_publication(
        local_site,
        {
            f"web/output/{path.relative_to(root).as_posix()}": path.read_bytes()
            for path in [root / "web_events.json", root / "occasions/year.json"]
        },
    )
    export_run({**data, "city_occasions": []}, root, now=now)
    with httpx.Client(base_url=local_site.url) as client:
        carry_forward_occasions(
            root,
            definitions=[],
            events=[event],
            now=now,
            client=client,
            repo="test/events",
        )
    manifest = json.loads((root / "web_events.json").read_text())
    assert manifest["concerts"] == []
    programme = json.loads((root / "occasions/year.json").read_text())
    assert len(programme["programme"]) == 1
    assert programme["programme"][0]["dateISO"] == "2027-01-02"


def test_run_recovers_and_retries_after_a_programme_upload_outlives_its_manifest(
    known_publication: tuple[OccasionDefinition, Event, dict[str, bytes]],
    monkeypatch: pytest.MonkeyPatch,
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    from boringhannover import github_sync

    prior, event, files = known_publication
    serve_github_publication(local_site, files, revision="c" * 40, tree_sha="d" * 40)
    for path, value in list(local_site.pages.items()):
        if "/contents/" in path:
            local_site.pages[f"{path}?ref={'c' * 40}"] = value
    serve_github_publication(local_site, files, parents=("c" * 40,))
    definition = replace(prior, description="Fresh source facts.")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        main,
        "fetch_all_events",
        lambda **_: {
            "movies_this_week": [],
            "big_events_radar": [event],
            "city_occasions": [definition],
            "source_outcomes": [FETCHED],
        },
    )
    monkeypatch.setattr(main, "should_sync", lambda: True)
    monkeypatch.setattr(main, "backup_run", lambda _: True)
    manifest_path = "/repos/test/events/contents/web/output/web_events.json"
    local_site.put_statuses[manifest_path] = 503
    with httpx.Client(base_url=local_site.url) as client:

        def reconcile(output_dir: str, **kwargs: object) -> None:
            github_sync.carry_forward_occasions(
                output_dir, client=client, repo="test/events", **kwargs
            )

        def publish(output_dir: str) -> bool:
            try:
                return all(
                    _sync_file(client, "test/events", path, remote)
                    for path, remote in _collect_web_sync_paths(output_dir)
                )
            except httpx.HTTPStatusError:
                return False

        monkeypatch.setattr(main, "carry_forward_occasions", reconcile)
        monkeypatch.setattr(main, "sync_web_data_to_github", publish)
        assert main.run() is False
        assert [path for path, _ in local_site.puts] == [
            "/repos/test/events/contents/web/output/occasions/known.json",
            manifest_path,
        ]
        # The service persisted the programme PUT but rejected the manifest PUT.
        for path, payload in local_site.puts:
            if path != manifest_path:
                files[path.removeprefix("/repos/test/events/contents/")] = (
                    base64.b64decode(str(payload["content"]))
                )
        serve_github_publication(local_site, files, parents=("c" * 40,))
        local_site.put_statuses.clear()
        local_site.puts.clear()
        assert main.run() is True
    assert local_site.puts[-1][0] == manifest_path
    published = json.loads(base64.b64decode(str(local_site.puts[-1][1]["content"])))
    assert published["occasions"][0]["description"] == definition.description
    assert any(path.endswith(f"?ref={'c' * 40}") for path in local_site.requests)


@pytest.mark.parametrize(
    "history",
    ["coherent-head", "nearest-coherent", "changed-manifest", "unavailable-parent"],
)
def test_recovery_preserves_programme_only_updates_without_rewinding_new_manifests(
    history: str,
    known_publication: tuple[OccasionDefinition, Event, dict[str, bytes]],
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    from boringhannover.publication import read_published_occasions

    definition, event, _ = known_publication
    root = tmp_path / "versions"
    export_run(
        {
            "movies_this_week": [],
            "big_events_radar": [
                replace(
                    event,
                    title=f"Known festival show {index}",
                    date=event.date + timedelta(minutes=index),
                    metadata={"occasion_id": definition.id},
                )
                for index in range(4)
            ],
            "city_occasions": [definition],
            "source_outcomes": [FETCHED],
        },
        root,
    )
    manifest = (root / "web_events.json").read_bytes()
    programme = json.loads((root / "occasions/known.json").read_bytes())
    files = {
        "web/output/web_events.json": manifest,
        "web/output/occasions/known.json": json.dumps(programme).encode(),
    }
    programme["programme"][-1]["status"] = "cancelled"
    updated = {
        **files,
        "web/output/occasions/known.json": json.dumps(programme).encode(),
    }
    mixed = json.loads(updated["web/output/occasions/known.json"])
    mixed["occasion"]["description"] = "Upload not yet referenced by the manifest."
    head = {**updated, "web/output/occasions/known.json": json.dumps(mixed).encode()}
    if history == "coherent-head":
        head = updated
    if history == "changed-manifest":
        old_manifest = json.loads(manifest)
        old_manifest["occasions"][0]["name"] = "An older publication"
        updated["web/output/web_events.json"] = json.dumps(old_manifest).encode()
    for revision, tree_sha, snapshot, parents in [
        ("e" * 40, "f" * 40, files, ()),
        ("c" * 40, "d" * 40, updated, ("e" * 40,)),
        ("a" * 40, "b" * 40, head, ("c" * 40,)),
    ]:
        serve_github_publication(
            local_site, snapshot, revision=revision, tree_sha=tree_sha, parents=parents
        )
        for path, value in list(local_site.pages.items()):
            if "/contents/" in path and "?" not in path:
                local_site.pages[f"{path}?ref={revision}"] = value
    if history == "unavailable-parent":
        local_site.pages[f"/repos/test/events/commits/{'c' * 40}"] = (503, "{}")
    with httpx.Client(base_url=local_site.url) as client:
        if history == "changed-manifest":
            with pytest.raises(ValueError, match="rewinding a changed"):
                read_published_occasions(client, "test/events")
        elif history == "unavailable-parent":
            with pytest.raises(httpx.HTTPStatusError):
                read_published_occasions(client, "test/events")
        else:
            restored = read_published_occasions(client, "test/events")
            assert restored[definition.id]["programme"][-1]["status"] == "cancelled"
            assert f"/repos/test/events/commits/{'e' * 40}" not in local_site.requests
            if history == "coherent-head":
                assert (
                    f"/repos/test/events/commits/{'c' * 40}" not in local_site.requests
                )


@pytest.mark.parametrize(
    "fault",
    [
        "inaccessible-repo",
        "manifest-404",
        "manifest-503",
        "malformed-json",
        "invalid-number",
        "duplicate-key",
        "missing-programme",
        "mixed-summaries",
        "duplicate-identity",
        "unsafe-path",
        "invalid-schedule",
        "symlink",
        "truncated-tree",
        "wrong-blob",
        "oversized-file",
        "partial-discovery",
        "local-run",
    ],
)
def test_run_never_backs_up_or_publishes_unvalidated_prior_state(
    fault: str,
    known_publication: tuple[OccasionDefinition, Event, dict[str, bytes]],
    monkeypatch: pytest.MonkeyPatch,
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    from boringhannover import github_sync

    _, event, files = known_publication
    manifest_path = "web/output/web_events.json"
    programme_path = "web/output/occasions/known.json"
    manifest = json.loads(files[manifest_path])
    if fault == "malformed-json":
        files[manifest_path] = b"{broken"
    elif fault == "invalid-number":
        files[manifest_path] = files[manifest_path][:-1] + b', "bad": NaN}'
    elif fault == "duplicate-key":
        files[manifest_path] = files[manifest_path][:-1] + b', "occasions": []}'
    elif fault == "missing-programme":
        del files[programme_path]
    elif fault == "mixed-summaries":
        programme = json.loads(files[programme_path])
        programme["occasion"]["name"] = "New facts uploaded before the manifest"
        files[programme_path] = json.dumps(programme).encode()
    elif fault == "duplicate-identity":
        manifest["occasions"].append(manifest["occasions"][0])
        files[manifest_path] = json.dumps(manifest).encode()
    elif fault == "unsafe-path":
        manifest["occasions"][0]["programmePath"] = "occasions/../../outside.json"
        files[manifest_path] = json.dumps(manifest).encode()
    elif fault == "invalid-schedule":
        manifest["occasions"][0]["occurrences"] = [
            {"date": event.date.date().isoformat(), "startTime": "25:70"}
        ]
        files[manifest_path] = json.dumps(manifest).encode()
    elif fault == "oversized-file":
        files[manifest_path] = b" " * (1024 * 1024 + 1)
    serve_github_publication(local_site, files)
    if fault == "inaccessible-repo":
        local_site.pages["/repos/test/events"] = (404, "{}")
    elif fault in ("manifest-404", "manifest-503"):
        local_site.pages[f"/repos/test/events/contents/{manifest_path}"] = (
            404 if fault == "manifest-404" else 503,
            "{}",
        )
    elif fault in ("symlink", "truncated-tree"):
        path = f"/repos/test/events/git/trees/{'b' * 40}"
        tree = json.loads(local_site.pages[path][1])
        if fault == "symlink":
            tree["tree"][0]["mode"] = "120000"
        else:
            tree["truncated"] = True
        local_site.pages[path] = (200, json.dumps(tree))
    elif fault == "wrong-blob":
        path = f"/repos/test/events/contents/{manifest_path}"
        payload = json.loads(local_site.pages[path][1])
        payload["sha"] = "f" * 40
        local_site.pages[path] = (200, json.dumps(payload))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        main,
        "fetch_all_events",
        lambda **_: {
            "movies_this_week": [],
            "big_events_radar": [event],
            "city_occasions": [],
            "source_outcomes": [FETCHED, PARTIAL]
            if fault == "partial-discovery"
            else [FETCHED],
        },
    )
    monkeypatch.setattr(main, "should_sync", lambda: True)
    calls = []
    monkeypatch.setattr(main, "backup_run", lambda _: calls.append("backup") or True)
    monkeypatch.setattr(
        main, "sync_web_data_to_github", lambda _: calls.append("sync") or True
    )
    with httpx.Client(base_url=local_site.url) as client:

        def reconcile(output_dir: str, **kwargs: object) -> None:
            github_sync.carry_forward_occasions(
                output_dir, client=client, repo="test/events", **kwargs
            )

        monkeypatch.setattr(main, "carry_forward_occasions", reconcile)
        assert main.run(local=fault == "local-run") is (fault == "local-run")
    assert calls == []
    assert local_site.puts == []
    assert (tmp_path / "output/web_events.json").exists()
    if fault in ("partial-discovery", "local-run"):
        assert local_site.requests == []


@pytest.mark.parametrize(
    "change",
    [
        "rolling-start",
        "rolling-sparse",
        "rolling-sparse-extended",
        "cancelled",
        "cancelled-with-new-date",
        "postponed",
        "rescheduled",
        "rescheduled-outside-window",
        "source-ended",
        "omitted-unknown",
        "omitted-cancelled",
        "cancellation-marker-disappears",
        "unexplained-shift",
        "identity-collision",
        "inventory-overflow",
    ],
)
def test_current_source_evidence_wins_without_reinventing_old_facts(
    change: str,
    known_publication: tuple[OccasionDefinition, Event, dict[str, bytes]],
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    from boringhannover.github_sync import carry_forward_occasions

    prior, event, files = known_publication
    now = datetime.now(BERLIN_TZ)
    today = now.date()
    current = prior
    definitions = []
    if change == "rolling-start":
        current = replace(prior, start_date=today)
    elif change in ("rolling-sparse", "rolling-sparse-extended"):
        dates = [prior.start_date, today + timedelta(days=4), today + timedelta(days=5)]
        manifest = json.loads(files["web/output/web_events.json"])
        programme = json.loads(files["web/output/occasions/known.json"])
        for row in (manifest["occasions"][0], programme["occasion"]):
            row["scheduleConfidence"] = "discrete"
            row["occurrences"] = [{"date": day.isoformat()} for day in dates]
        files["web/output/web_events.json"] = json.dumps(manifest).encode()
        files["web/output/occasions/known.json"] = json.dumps(programme).encode()
        remaining = dates[1:] + (
            [today + timedelta(days=14)] if change == "rolling-sparse-extended" else []
        )
        current = replace(
            prior,
            start_date=dates[1],
            end_date=remaining[-1],
            schedule_confidence="discrete",
            occurrences=tuple(Occurrence(day) for day in remaining),
        )
    elif change in ("cancelled", "postponed"):
        current = replace(prior, source_status=change)
    elif change == "cancelled-with-new-date":
        current = replace(
            prior, source_status="cancelled", start_date=today + timedelta(days=1)
        )
    elif change in ("rescheduled", "rescheduled-outside-window"):
        offset = 2 if change == "rescheduled" else 30
        current = replace(
            prior,
            start_date=today + timedelta(days=offset),
            end_date=today + timedelta(days=offset + 1),
            source_status="rescheduled",
            previous_start_date=prior.start_date,
        )
    elif change == "source-ended":
        current = replace(prior, end_date=today - timedelta(days=1))
    elif change == "unexplained-shift":
        current = replace(prior, start_date=today + timedelta(days=1))
    elif change == "identity-collision":
        current = replace(prior, id="test:different-identity")
    elif change == "cancellation-marker-disappears":
        current = replace(prior, source_status=None)
        manifest = json.loads(files["web/output/web_events.json"])
        programme = json.loads(files["web/output/occasions/known.json"])
        manifest["occasions"][0]["sourceStatus"] = "cancelled"
        programme["occasion"]["sourceStatus"] = "cancelled"
        files["web/output/web_events.json"] = json.dumps(manifest).encode()
        files["web/output/occasions/known.json"] = json.dumps(programme).encode()
    if not change.startswith("omitted-"):
        definitions = [current]
    else:
        manifest = json.loads(files["web/output/web_events.json"])
        programme = json.loads(files["web/output/occasions/known.json"])
        for row in (manifest["occasions"][0], programme["occasion"]):
            if change == "omitted-unknown":
                row["scheduleConfidence"] = "unknown"
            else:
                row["sourceStatus"] = "cancelled"
        files["web/output/web_events.json"] = json.dumps(manifest).encode()
        files["web/output/occasions/known.json"] = json.dumps(programme).encode()
    if change == "inventory-overflow":
        definitions = [
            replace(
                prior,
                id=f"test:new-{index}",
                slug=f"new-{index}",
                name=f"Different festival {index}",
                source_url=f"https://example.com/new-{index}",
            )
            for index in range(100)
        ]
    serve_github_publication(local_site, files)
    root = tmp_path / "candidate"
    export_run(
        {
            "movies_this_week": [],
            "big_events_radar": [event],
            "city_occasions": definitions,
            "source_outcomes": [FETCHED],
        },
        root,
        now=now,
    )
    with httpx.Client(base_url=local_site.url) as client:
        if change in ("unexplained-shift", "identity-collision", "inventory-overflow"):
            before = (root / "web_events.json").read_bytes()
            with pytest.raises(ValueError, match=r"Conflicting|conflict|exceeds"):
                carry_forward_occasions(
                    root,
                    definitions=definitions,
                    now=now,
                    client=client,
                    repo="test/events",
                )
            assert (root / "web_events.json").read_bytes() == before
            return
        carry_forward_occasions(
            root, definitions=definitions, now=now, client=client, repo="test/events"
        )
    data = json.loads((root / "web_events.json").read_text())
    if change in ("source-ended", "rescheduled-outside-window"):
        assert data["occasions"] == []
        return
    (summary,) = data["occasions"]
    assert summary["id"] == prior.id
    assert summary["slug"] == prior.slug
    assert summary["sourceUrl"] == prior.source_url
    assert (
        summary["startDate"]
        == (
            current.start_date
            if change in ("rescheduled", "cancelled-with-new-date")
            else prior.start_date
        ).isoformat()
    )
    if change in ("cancelled", "postponed", "rescheduled"):
        assert summary["sourceStatus"] == change
    if change == "cancelled-with-new-date":
        assert summary["sourceStatus"] == "cancelled"
    if change == "rescheduled":
        assert summary["previousStartDate"] == prior.start_date.isoformat()
    if change == "omitted-unknown":
        assert summary["scheduleConfidence"] == "unknown"
        assert "occurrences" not in summary
    if change in ("omitted-cancelled", "cancellation-marker-disappears"):
        assert summary["sourceStatus"] == "cancelled"
    programme = json.loads((root / summary["programmePath"]).read_text())
    assert programme["occasion"] == summary
    if change.startswith("omitted-") or change in (
        "rolling-start",
        "cancellation-marker-disappears",
    ):
        assert (
            programme["meta"]
            == json.loads(files["web/output/occasions/known.json"])["meta"]
        )


@pytest.mark.parametrize(
    ("clock", "end", "appointments", "expected"),
    [
        ("2026-10-25T00:30:00+00:00", "2026-10-25", None, True),
        ("2026-10-25T23:30:00+00:00", "2026-10-25", None, False),
        ("2026-12-31T22:30:00+00:00", "2026-12-31", None, True),
        ("2026-12-31T23:30:00+00:00", "2026-12-31", None, False),
        ("2026-11-02T12:00:00+01:00", "2026-11-07", (-1,), False),
        ("2026-11-02T12:00:00+01:00", "2026-11-07", (-1, 1), True),
    ],
    ids=[
        "dst-final-day",
        "dst-next-berlin-day",
        "year-final-day",
        "year-next-berlin-day",
        "sparse-appointments-exhausted",
        "sparse-only-confirmed-date-survives",
    ],
)
def test_carry_forward_obeys_berlin_dates_and_confirmed_sparse_appointments(
    clock: str,
    end: str,
    appointments: tuple[int, ...] | None,
    expected: bool,
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    from boringhannover.github_sync import carry_forward_occasions

    now = datetime.fromisoformat(clock)
    today = now.astimezone(BERLIN_TZ).date()
    prior_time = (now.astimezone(BERLIN_TZ) - timedelta(days=2)).replace(hour=12)
    occasion = OccasionDefinition(
        id="test:clock",
        slug="clock",
        name="Clock festival",
        kind="festival",
        start_date=today - timedelta(days=3),
        end_date=datetime.fromisoformat(end).date(),
        location="Hannover",
        source_url="https://example.com/clock",
        description="Clock fixture.",
        schedule_confidence="discrete" if appointments is not None else "continuous",
        occurrences=tuple(
            Occurrence(today + timedelta(days=offset)) for offset in appointments or ()
        ),
    )
    root = tmp_path / "output"
    export_run(
        {
            "movies_this_week": [],
            "big_events_radar": [],
            "city_occasions": [occasion],
            "source_outcomes": [],
        },
        root,
        now=prior_time,
    )
    files = {
        f"web/output/{path.relative_to(root).as_posix()}": path.read_bytes()
        for path in [root / "web_events.json", root / "occasions/clock.json"]
    }
    serve_github_publication(local_site, files)
    # If the branch advances between requests, only the pinned responses are coherent.
    for path, value in list(local_site.pages.items()):
        if "/contents/" in path:
            local_site.pages[f"{path}?ref={'a' * 40}"] = value
            local_site.pages[path] = (200, '{"branch":"advanced"}')
    export_run(
        {
            "movies_this_week": [],
            "big_events_radar": [],
            "city_occasions": [],
            "source_outcomes": [],
        },
        root,
        now=now,
    )
    with httpx.Client(base_url=local_site.url) as client:
        carry_forward_occasions(
            root, definitions=[], now=now, client=client, repo="test/events"
        )
    data = json.loads((root / "web_events.json").read_text())
    assert bool(data["occasions"]) is expected
    if expected:
        (summary,) = data["occasions"]
        assert summary["startDate"] == occasion.start_date.isoformat()
        assert summary["endDate"] == end
        assert "imageUrl" not in summary
        if appointments is not None:
            assert summary["occurrences"] == [
                {"date": (today + timedelta(days=1)).isoformat()}
            ]
        retained = json.loads((root / "occasions/clock.json").read_text())
        assert (
            retained["meta"]
            == json.loads(files["web/output/occasions/clock.json"])["meta"]
        )
