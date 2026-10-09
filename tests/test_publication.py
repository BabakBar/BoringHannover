"""A production run that cannot publish or back up must not report success.

The site serves whatever was last committed, so a run that scrapes but fails
to sync leaves stale data up. Reporting success there hides the outage from
the scheduler, which is how the 28 Aug data stayed live for two run cycles.
"""

from __future__ import annotations

import json

import pytest

from boringhannover import main
from boringhannover.github_sync import (
    WEB_EVENTS_REPO_PATH,
    WEB_OCCASIONS_REPO_DIR,
    _collect_web_sync_paths,
    _normalize_events_json,
)


@pytest.mark.parametrize(
    ("local", "sync_configured", "sync_ok", "backup_ok", "succeeded", "calls"),
    [
        pytest.param(False, True, True, True, True, ["backup", "sync"], id="ok"),
        pytest.param(
            False, True, False, True, False, ["backup", "sync"], id="sync-fails"
        ),
        pytest.param(
            False, False, True, True, False, ["backup"], id="sync-not-configured"
        ),
        # Fresh data still goes out; the gap in the history fails the run.
        pytest.param(
            False, True, True, False, False, ["backup", "sync"], id="backup-fails"
        ),
        pytest.param(True, False, False, False, True, [], id="local-skips-both"),
    ],
)
def test_run_reports_publication_and_backup_failures(
    monkeypatch: pytest.MonkeyPatch,
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
        lambda: {"movies_this_week": [], "big_events_radar": []},
    )
    monkeypatch.setattr(main, "export_run", lambda _events: None)
    monkeypatch.setattr(main, "backup_run", backup)
    monkeypatch.setattr(main, "should_sync", lambda: sync_configured)
    monkeypatch.setattr(main, "sync_web_data_to_github", sync)

    assert main.run(local=local) is succeeded
    assert recorded == calls


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
