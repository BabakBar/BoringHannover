"""Tests for generated web-data synchronization ordering."""

from __future__ import annotations

from boringhannover.github_sync import (
    WEB_EVENTS_REPO_PATH,
    WEB_OCCASIONS_REPO_DIR,
    _collect_web_sync_paths,
)


def test_collect_web_sync_paths_puts_manifest_last(tmp_path) -> None:
    occasions = tmp_path / "occasions"
    occasions.mkdir()
    (occasions / "z-event.json").write_text("{}", encoding="utf-8")
    (occasions / "a-event.json").write_text("{}", encoding="utf-8")
    (tmp_path / "web_events.json").write_text("{}", encoding="utf-8")

    paths = _collect_web_sync_paths(tmp_path)

    assert [path.name for path, _ in paths] == [
        "a-event.json",
        "z-event.json",
        "web_events.json",
    ]
    assert [repo_path for _, repo_path in paths] == [
        f"{WEB_OCCASIONS_REPO_DIR}/a-event.json",
        f"{WEB_OCCASIONS_REPO_DIR}/z-event.json",
        WEB_EVENTS_REPO_PATH,
    ]
