"""Tests for the repository traffic archiver and dashboard generator."""

from __future__ import annotations

import sys
from pathlib import Path


# Add scripts directory to path to import capture_traffic
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from capture_traffic import (  # noqa: E402
    generate_interactive_dashboard,
    generate_markdown_report,
    merge_paths,
    merge_referrers,
    merge_time_series,
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


def test_generate_markdown_report_includes_kpis_and_tables() -> None:
    """Report contains formatted KPI values and markdown tables."""
    summary = {
        "repository": "BabakBar/BoringHannover",
        "last_updated_utc": "2026-08-20T12:00:00Z",
        "history_start_date": "2026-08-01",
        "history_end_date": "2026-08-14",
        "total_days_recorded": 14,
        "all_time_views": 1500,
        "all_time_unique_visitors": 800,
        "all_time_clones": 350,
        "all_time_unique_cloners": 120,
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

    md = generate_markdown_report(summary, views, clones, referrers, paths, stargazers)

    assert "# 📊 Repository Traffic & Analytics — BabakBar/BoringHannover" in md
    assert "1,500" in md  # Views formatted with commas
    assert "github.com" in md
    assert "/README.md" in md
    assert "@alice" in md


def test_generate_interactive_dashboard_contains_charts_and_data() -> None:
    """Interactive HTML dashboard renders with embedded datasets and Chart.js canvas."""
    summary = {
        "repository": "BabakBar/BoringHannover",
        "all_time_views": 100,
        "all_time_unique_visitors": 50,
        "all_time_clones": 200,
        "all_time_unique_cloners": 80,
        "current_stars": 5,
        "current_forks": 1,
    }

    html = generate_interactive_dashboard(summary, [], [], {}, {}, [])

    assert "<!DOCTYPE html>" in html
    assert "chart.umd.min.js" in html
    assert "viewsChart" in html
    assert "clonesChart" in html
    assert "growthChart" in html
    assert "referrersChart" in html
    assert "starsChart" in html
    assert "BabakBar/BoringHannover" in html
