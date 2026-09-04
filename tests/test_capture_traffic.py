"""Tests for the repository traffic archiver and dashboard generator."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


# Add scripts directory to path to import capture_traffic
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from capture_traffic import (  # noqa: E402
    TrafficCaptureError,
    generate_markdown_report,
    load_json,
    merge_keyed,
    merge_paths,
    merge_referrers,
    merge_time_series,
    render_dashboard,
    require_token,
    window,
)


def test_merge_time_series_lossless_and_monotonic() -> None:
    """Historical dates are preserved and overlapping dates update monotonically."""
    existing = [
        {
            "date": "2026-08-01",
            "timestamp": "2026-08-01T00:00:00Z",
            "count": 10,
            "uniques": 5,
        },
        {
            "date": "2026-08-02",
            "timestamp": "2026-08-02T00:00:00Z",
            "count": 20,
            "uniques": 10,
        },
    ]

    # New snapshot: date 08-02 has higher in-progress count, date 08-03 is brand new
    new_data = [
        {"timestamp": "2026-08-02T00:00:00Z", "count": 25, "uniques": 12},
        {"timestamp": "2026-08-03T00:00:00Z", "count": 15, "uniques": 8},
    ]

    merged = merge_time_series(existing, new_data)

    assert len(merged) == 3
    # 2026-08-01 was not in new snapshot but is retained
    assert merged[0]["date"] == "2026-08-01"
    assert merged[0]["count"] == 10
    # 2026-08-02 count was updated to max(20, 25)
    assert merged[1]["date"] == "2026-08-02"
    assert merged[1]["count"] == 25
    assert merged[1]["uniques"] == 12
    # 2026-08-03 was added
    assert merged[2]["date"] == "2026-08-03"
    assert merged[2]["count"] == 15


def test_merge_referrers_accumulates_domain_stats() -> None:
    """Referrers preserve snapshots and maintain all-time peak and seen tracking."""
    existing = {
        "snapshots": [],
        "all_time": [
            {
                "referrer": "google.com",
                "latest_count": 5,
                "latest_uniques": 3,
                "max_count": 10,
                "max_uniques": 8,
                "first_seen": "2026-08-01",
                "last_seen": "2026-08-01",
            }
        ],
    }

    new_refs = [
        {"referrer": "google.com", "count": 12, "uniques": 9},
        {"referrer": "reddit.com", "count": 4, "uniques": 4},
    ]

    result = merge_referrers(existing, new_refs, "2026-08-15")

    assert len(result["snapshots"]) == 1
    assert result["snapshots"][0]["date"] == "2026-08-15"

    all_time = {r["referrer"]: r for r in result["all_time"]}
    assert "google.com" in all_time
    assert "reddit.com" in all_time

    # Peak count should increase to 12
    assert all_time["google.com"]["max_count"] == 12
    assert all_time["google.com"]["latest_count"] == 12
    assert all_time["google.com"]["first_seen"] == "2026-08-01"
    assert all_time["google.com"]["last_seen"] == "2026-08-15"

    # Brand new domain
    assert all_time["reddit.com"]["first_seen"] == "2026-08-15"
    assert all_time["reddit.com"]["max_count"] == 4


def test_merge_referrers_retains_domains_absent_from_the_snapshot() -> None:
    """A domain that drops out of GitHub's 14-day window keeps its recorded history."""
    existing = {
        "snapshots": [],
        "all_time": [
            {
                "referrer": "news.ycombinator.com",
                "latest_count": 90,
                "latest_uniques": 40,
                "max_count": 90,
                "max_uniques": 40,
                "first_seen": "2026-07-01",
                "last_seen": "2026-07-02",
            }
        ],
    }

    result = merge_referrers(
        existing, [{"referrer": "google.com", "count": 1}], "2026-08-15"
    )

    hn = next(r for r in result["all_time"] if r["referrer"] == "news.ycombinator.com")
    assert hn["max_count"] == 90
    assert hn["last_seen"] == "2026-07-02"


def test_merge_paths_tracks_popular_endpoints() -> None:
    """Path statistics retain maximum counts and record first and last seen timestamps."""
    existing = {"snapshots": [], "all_time": []}
    new_paths = [
        {
            "path": "/BabakBar/BoringHannover",
            "title": "Overview",
            "count": 42,
            "uniques": 18,
        }
    ]

    result = merge_paths(existing, new_paths, "2026-08-20")

    assert len(result["all_time"]) == 1
    entry = result["all_time"][0]
    assert entry["path"] == "/BabakBar/BoringHannover"
    assert entry["title"] == "Overview"
    assert entry["max_count"] == 42
    assert entry["latest_count"] == 42


def test_merge_keyed_never_drops_existing_records() -> None:
    """Stars and forks survive a snapshot that omits them (unstar, or a failed page)."""
    existing = [
        {
            "starred_at": "2025-12-16T21:04:50Z",
            "date": "2025-12-16",
            "user": "timohausmann",
        },
        {"starred_at": "2025-12-29T21:54:40Z", "date": "2025-12-29", "user": "emsy1"},
    ]
    # emsy1 unstarred; a new star arrived
    new = [
        {
            "starred_at": "2025-12-16T21:04:50Z",
            "date": "2025-12-16",
            "user": "timohausmann",
        },
        {"starred_at": "2026-07-27T07:25:01Z", "date": "2026-07-27", "user": "axsb"},
    ]

    merged = merge_keyed(existing, new, key="user", sort_field="starred_at")

    users = [record["user"] for record in merged]
    assert users == ["timohausmann", "emsy1", "axsb"]


def test_merge_keyed_rejects_an_empty_snapshot_silently_wiping_history() -> None:
    """An empty fetch result must not empty the archive."""
    existing = [{"user": "timohausmann", "starred_at": "2025-12-16T21:04:50Z"}]

    assert merge_keyed(existing, [], key="user", sort_field="starred_at") == existing


def test_load_json_raises_on_a_corrupt_archive(tmp_path: Path) -> None:
    """A truncated archive file is a stop condition, never a silent reset to empty."""
    corrupt = tmp_path / "views.json"
    corrupt.write_text('[{"date": "2026-08-01", "count": 3', encoding="utf-8")

    with pytest.raises(TrafficCaptureError, match=r"views\.json"):
        load_json(corrupt, default=[])


def test_load_json_returns_default_for_a_first_run(tmp_path: Path) -> None:
    """A missing file is the legitimate empty case."""
    assert load_json(tmp_path / "views.json", default=[]) == []


def test_window_selects_calendar_days_not_list_positions() -> None:
    """A gap in the archive must not stretch a 7-day window across weeks."""
    series = [
        {"date": "2026-06-01", "count": 1},
        {"date": "2026-06-02", "count": 1},
        {"date": "2026-08-28", "count": 5},
        {"date": "2026-08-30", "count": 7},
    ]

    selected = window(series, days=7, today="2026-09-03")

    assert [item["date"] for item in selected] == ["2026-08-28", "2026-08-30"]


def test_require_token_fails_loudly_when_unauthenticated() -> None:
    """The traffic API is unreachable without a token; capturing zeros is not a result."""
    with pytest.raises(TrafficCaptureError, match="TRAFFIC_TOKEN"):
        require_token("")


def test_generate_markdown_report_includes_kpis_and_tables() -> None:
    """Report contains formatted KPI values and markdown tables."""
    summary = {
        "repository": "BabakBar/BoringHannover",
        "last_updated_utc": "2026-08-20T12:00:00Z",
        "history_start_date": "2026-08-01",
        "history_end_date": "2026-08-14",
        "total_days_recorded": 14,
        "all_time_views": 1500,
        "sum_daily_unique_visitors": 800,
        "all_time_clones": 350,
        "sum_daily_unique_cloners": 120,
        "current_stars": 10,
        "current_forks": 3,
    }

    views = [{"date": "2026-08-14", "count": 100, "uniques": 50}]
    clones = [{"date": "2026-08-14", "count": 25, "uniques": 10}]
    referrers = {
        "all_time": [{"referrer": "github.com", "latest_count": 50, "max_count": 50}]
    }
    paths = {
        "all_time": [
            {
                "path": "/README.md",
                "title": "README",
                "latest_count": 20,
                "max_count": 20,
            }
        ]
    }
    stargazers = [{"date": "2026-08-10", "user": "alice"}]

    md = generate_markdown_report(
        summary, views, clones, referrers, paths, stargazers, today="2026-08-20"
    )

    assert "# 📊 Repository Traffic & Analytics — BabakBar/BoringHannover" in md
    assert "1,500" in md  # Views formatted with commas
    assert "github.com" in md
    assert "/README.md" in md
    assert "@alice" in md
    # The summed-uniques figure must not be labelled as a distinct-visitor count
    assert "Unique Visitors (summed daily)" in md


def test_markdown_report_caps_the_stargazer_table() -> None:
    """The report is regenerated twice daily; the star table cannot grow without bound."""
    stargazers = [
        {"date": "2026-01-01", "user": f"user{i}", "starred_at": "2026-01-01T00:00:00Z"}
        for i in range(120)
    ]

    md = generate_markdown_report(
        {"repository": "r"}, [], [], {}, {}, stargazers, today="2026-08-20"
    )

    assert md.count("| @user") <= 50
    assert "120" in md  # the true total is still reported


def _extract_app_script(html: str) -> str:
    match = re.search(
        r'<script id="dashboard-app">(.*?)</script>', html, flags=re.DOTALL
    )
    assert match, "dashboard app script block not found"
    return match.group(1)


def test_dashboard_embeds_data_and_chart_canvases() -> None:
    """Interactive HTML dashboard renders with embedded datasets and Chart.js canvases."""
    summary = {
        "repository": "BabakBar/BoringHannover",
        "all_time_views": 100,
        "sum_daily_unique_visitors": 50,
        "all_time_clones": 200,
        "sum_daily_unique_cloners": 80,
        "current_stars": 5,
        "current_forks": 1,
    }

    html = render_dashboard(summary, [], [], {}, {}, [], today="2026-09-05")

    assert "<!DOCTYPE html>" in html
    assert "chart.umd.min.js" in html
    for canvas in (
        "viewsChart",
        "clonesChart",
        "growthChart",
        "referrersChart",
        "starsChart",
    ):
        assert f'id="{canvas}"' in html
    assert "BabakBar/BoringHannover" in html


@pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required to parse the dashboard"
)
def test_dashboard_script_is_valid_javascript(tmp_path: Path) -> None:
    """A syntax error anywhere in the block silently disables the whole dashboard."""
    html = render_dashboard(
        {"repository": "BabakBar/BoringHannover"},
        [{"date": "2026-09-01", "count": 3, "uniques": 2}],
        [{"date": "2026-09-01", "count": 9, "uniques": 4}],
        {"all_time": [{"referrer": "google.com", "latest_count": 2, "max_count": 2}]},
        {"all_time": [{"path": "/x", "title": "X", "latest_count": 1, "max_count": 1}]},
        [{"date": "2026-01-01", "user": "alice", "starred_at": "2026-01-01T00:00:00Z"}],
        today="2026-09-05",
    )

    script = tmp_path / "dashboard.js"
    script.write_text(_extract_app_script(html), encoding="utf-8")

    result = subprocess.run(
        ["node", "--check", str(script)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_dashboard_neutralises_a_script_closing_tag_in_third_party_data() -> None:
    """Referrer domains are attacker-chosen; they must not be able to close the data block."""
    hostile = "evil.com</script><script>alert(1)</script>"
    html = render_dashboard(
        {"repository": "r"},
        [],
        [],
        {"all_time": [{"referrer": hostile, "latest_count": 1, "max_count": 1}]},
        {},
        [],
        today="2026-09-05",
    )

    assert "</script><script>alert(1)" not in html
    # The value still round-trips as data
    payload = re.search(
        r'<script id="traffic-data" type="application/json">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert payload
    assert json.loads(payload.group(1))["referrers"][0]["referrer"] == hostile
