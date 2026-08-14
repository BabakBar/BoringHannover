"""Timestamp contract behind the sitemap's <lastmod>.

The frontend derives <lastmod> from meta.updatedAtISO. meta.updatedAt is a
display string ("Sun 26 Jul 16:08") that parses to the year 2001, so a
regression that drops the ISO field would silently ship wrong dates -- and
Google discounts lastmod across a whole sitemap once it looks unreliable.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from boringhannover.constants import BERLIN_TZ
from boringhannover.exporters import export_web_json
from boringhannover.github_sync import _normalize_events_json


@pytest.fixture
def web_meta(tmp_path: Path) -> dict:
    export_web_json(
        [],
        [],
        tmp_path,
        31,
        2026,
        generated_at=datetime(2026, 7, 26, 16, 8, tzinfo=BERLIN_TZ),
    )
    data = json.loads((tmp_path / "web_events.json").read_text())
    return data["meta"]


def test_web_json_exposes_machine_readable_timestamp(web_meta: dict) -> None:
    assert datetime.fromisoformat(web_meta["updatedAtISO"]) == datetime(
        2026, 7, 26, 16, 8, tzinfo=BERLIN_TZ
    )


def test_display_and_iso_timestamps_describe_the_same_instant(
    web_meta: dict,
) -> None:
    parsed = datetime.fromisoformat(web_meta["updatedAtISO"])
    assert parsed.strftime("%a %d %b %H:%M") == web_meta["updatedAt"]


def test_display_timestamp_alone_is_not_a_usable_lastmod(web_meta: dict) -> None:
    """Guards the reason updatedAtISO exists at all."""
    with pytest.raises(ValueError):
        datetime.fromisoformat(web_meta["updatedAt"])


def test_sync_ignores_both_timestamps_when_detecting_changes() -> None:
    """Otherwise every scrape commits, redeploys, and moves lastmod for nothing."""
    same_content = {"meta": {"week": 31, "year": 2026}, "movies": []}

    earlier = dict(same_content)
    earlier["meta"] = {
        **same_content["meta"],
        "updatedAt": "Sun 26 Jul 16:08",
        "updatedAtISO": "2026-07-26T16:08:00+02:00",
    }
    later = dict(same_content)
    later["meta"] = {
        **same_content["meta"],
        "updatedAt": "Fri 14 Aug 09:01",
        "updatedAtISO": "2026-08-14T09:01:49+02:00",
    }

    assert _normalize_events_json(
        json.dumps(earlier).encode()
    ) == _normalize_events_json(json.dumps(later).encode())


def test_sync_still_detects_real_content_changes() -> None:
    base = {"meta": {"week": 31, "updatedAtISO": "2026-07-26T16:08:00+02:00"}}
    changed = {
        "meta": {"week": 31, "updatedAtISO": "2026-07-26T16:08:00+02:00"},
        "movies": ["something new"],
    }

    assert _normalize_events_json(json.dumps(base).encode()) != _normalize_events_json(
        json.dumps(changed).encode()
    )
