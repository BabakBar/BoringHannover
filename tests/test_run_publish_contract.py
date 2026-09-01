"""A production run that cannot publish must not report success.

The site serves whatever was last committed, so a run that scrapes but fails
to sync leaves stale data up. Reporting success there hides the outage from
the scheduler, which is how the 28 Aug data stayed live for two run cycles.
"""

from __future__ import annotations

import pytest

from boringhannover import main


@pytest.fixture
def stub_scrape(monkeypatch) -> None:
    """Make everything up to the sync step succeed."""
    monkeypatch.setattr(
        main,
        "fetch_all_events",
        lambda: {"movies_this_week": [], "big_events_radar": []},
    )
    monkeypatch.setattr(main, "notify", lambda _events: True)


def test_run_fails_when_sync_fails(stub_scrape, monkeypatch) -> None:
    monkeypatch.setattr(main, "should_sync", lambda: True)
    monkeypatch.setattr(main, "sync_web_data_to_github", lambda _dir: False)

    assert main.run(local=False) is False


def test_run_fails_when_sync_is_not_configured(stub_scrape, monkeypatch) -> None:
    monkeypatch.setattr(main, "should_sync", lambda: False)

    assert main.run(local=False) is False


def test_run_succeeds_when_sync_succeeds(stub_scrape, monkeypatch) -> None:
    synced: list[str] = []

    def _sync(output_dir: str) -> bool:
        synced.append(output_dir)
        return True

    monkeypatch.setattr(main, "should_sync", lambda: True)
    monkeypatch.setattr(main, "sync_web_data_to_github", _sync)

    assert main.run(local=False) is True
    assert synced == ["output"]


def test_local_run_does_not_require_sync(stub_scrape, monkeypatch) -> None:
    def _fail(_dir: str) -> bool:
        msg = "local runs must not sync"
        raise AssertionError(msg)

    monkeypatch.setattr(main, "should_sync", lambda: False)
    monkeypatch.setattr(main, "sync_web_data_to_github", _fail)

    assert main.run(local=True) is True
