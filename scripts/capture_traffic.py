#!/usr/bin/env python3
"""Capture, merge, and visualize GitHub repository traffic for all-time analytics.

Bypasses GitHub's 14-day data retention limit by persistently archiving
daily snapshots of views, clones, referrers, popular content paths,
stargazers, and forks.

Every failure is fatal. A partial capture that still writes its output would
overwrite the archive with a degraded snapshot, and the workflow would report
success -- the archive is the only copy of anything older than 14 days.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


TEMPLATE_PATH = Path(__file__).with_name("dashboard_template.html")
DATA_PLACEHOLDER = "__TRAFFIC_DATA__"
STAR_TABLE_LIMIT = 50
TABLE_LIMIT = 15
PER_PAGE = 100


class TrafficCaptureError(RuntimeError):
    """A metric could not be captured, so the archive must not be rewritten."""


def get_auth_token(explicit_token: str | None = None) -> str:
    """Resolve GitHub token from arguments, environment, or GitHub CLI."""
    if explicit_token:
        return explicit_token

    for env_var in ("TRAFFIC_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        token = os.getenv(env_var, "").strip()
        if token:
            return token

    try:
        proc = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return proc.stdout.strip()


def require_token(token: str) -> str:
    """Fail before any write when there is no usable credential."""
    if not token:
        raise TrafficCaptureError(
            "No GitHub token available. Set TRAFFIC_TOKEN to a PAT with "
            "'Administration: read' on this repository; the traffic API rejects "
            "unauthenticated requests and the default GITHUB_TOKEN."
        )
    return token


def github_api_get(
    endpoint: str, token: str, accept: str = "application/vnd.github.v3+json"
) -> Any:
    """Perform a GET request to the GitHub API."""
    url = f"https://api.github.com{endpoint}" if endpoint.startswith("/") else endpoint
    req = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "BoringHannover-Traffic-Archiver/1.0",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        error_body = err.read().decode("utf-8", errors="replace")
        raise TrafficCaptureError(
            f"GitHub API error {err.code} on {endpoint}: {error_body}"
        ) from err
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
        raise TrafficCaptureError(
            f"GitHub API request failed on {endpoint}: {err}"
        ) from err


def load_json(path: Path, default: Any) -> Any:
    """Load an archive file, treating a corrupt one as fatal rather than empty."""
    if not path.exists():
        return default

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as err:
        raise TrafficCaptureError(
            f"Existing archive {path.name} is unreadable ({err}). Refusing to "
            "continue: a fresh capture would overwrite it with a 14-day window."
        ) from err


def save_json(path: Path, data: Any) -> None:
    """Save data to JSON file with formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    """Save rows to CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def window(items: list[dict[str, Any]], days: int, today: str) -> list[dict[str, Any]]:
    """Select the last `days` calendar days, by date rather than list position.

    Slicing by position silently widens a window whenever the archive has a gap
    (a disabled workflow, an expired token), which is exactly when a long-range
    view matters most.
    """
    if days <= 0:
        return list(items)
    start = date.fromisoformat(today) - timedelta(days=days - 1)
    cutoff = start.isoformat()
    return [item for item in items if item.get("date", "") >= cutoff]


def merge_time_series(
    existing_items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
    key_field: str = "timestamp",
    count_fields: tuple[str, ...] = ("count", "uniques"),
) -> list[dict[str, Any]]:
    """Merge time-series data (views or clones) losslessly by date."""
    merged: dict[str, dict[str, Any]] = {}

    for item in existing_items:
        ts = item[key_field]
        date_str = ts[:10]
        merged[date_str] = {
            "date": date_str,
            "timestamp": f"{date_str}T00:00:00Z",
            **{cf: int(item.get(cf, 0)) for cf in count_fields},
        }

    for item in new_items:
        ts = item[key_field]
        date_str = ts[:10]
        new_counts = {cf: int(item.get(cf, 0)) for cf in count_fields}

        if date_str not in merged:
            merged[date_str] = {
                "date": date_str,
                "timestamp": f"{date_str}T00:00:00Z",
                **new_counts,
            }
        else:
            # Take the maximum so in-progress days can increase and historical counts never decrease
            for cf in count_fields:
                merged[date_str][cf] = max(merged[date_str][cf], new_counts[cf])

    return sorted(merged.values(), key=lambda x: x["date"])


def merge_keyed(
    existing_items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
    key: str,
    sort_field: str,
) -> list[dict[str, Any]]:
    """Merge stargazer or fork records without ever dropping a recorded one.

    Both endpoints return the *current* state, so a plain overwrite loses the
    timestamp of anyone who unstars, and loses everything if a page ever fails.
    """
    merged = {item[key]: item for item in existing_items}
    for item in new_items:
        merged[item[key]] = item
    return sorted(merged.values(), key=lambda item: str(item.get(sort_field, "")))


def merge_referrers(
    existing_data: dict[str, Any],
    new_referrers: list[dict[str, Any]],
    today_str: str,
) -> dict[str, Any]:
    """Merge 14-day referrer snapshots and track all-time domain statistics."""
    snapshots = existing_data.get("snapshots", [])
    all_time = {item["referrer"]: item for item in existing_data.get("all_time", [])}

    filtered_snapshots = [s for s in snapshots if s.get("date") != today_str]
    filtered_snapshots.append(
        {
            "date": today_str,
            "timestamp": f"{today_str}T00:00:00Z",
            "referrers": new_referrers,
        }
    )
    filtered_snapshots.sort(key=lambda s: s["date"])

    for ref in new_referrers:
        domain = ref.get("referrer", "unknown")
        count = int(ref.get("count", 0))
        uniques = int(ref.get("uniques", 0))

        if domain not in all_time:
            all_time[domain] = {
                "referrer": domain,
                "latest_count": count,
                "latest_uniques": uniques,
                "max_count": count,
                "max_uniques": uniques,
                "first_seen": today_str,
                "last_seen": today_str,
            }
        else:
            entry = all_time[domain]
            entry["latest_count"] = count
            entry["latest_uniques"] = uniques
            entry["max_count"] = max(entry.get("max_count", 0), count)
            entry["max_uniques"] = max(entry.get("max_uniques", 0), uniques)
            entry["last_seen"] = today_str

    sorted_all_time = sorted(
        all_time.values(), key=lambda x: x.get("max_count", 0), reverse=True
    )

    return {
        "last_updated": today_str,
        "snapshots": filtered_snapshots,
        "all_time": sorted_all_time,
    }


def merge_paths(
    existing_data: dict[str, Any],
    new_paths: list[dict[str, Any]],
    today_str: str,
) -> dict[str, Any]:
    """Merge 14-day path snapshots and track all-time popular path statistics."""
    snapshots = existing_data.get("snapshots", [])
    all_time = {item["path"]: item for item in existing_data.get("all_time", [])}

    filtered_snapshots = [s for s in snapshots if s.get("date") != today_str]
    filtered_snapshots.append(
        {
            "date": today_str,
            "timestamp": f"{today_str}T00:00:00Z",
            "paths": new_paths,
        }
    )
    filtered_snapshots.sort(key=lambda s: s["date"])

    for p in new_paths:
        path_name = p.get("path", "")
        title = p.get("title", "")
        count = int(p.get("count", 0))
        uniques = int(p.get("uniques", 0))

        if path_name not in all_time:
            all_time[path_name] = {
                "path": path_name,
                "title": title,
                "latest_count": count,
                "latest_uniques": uniques,
                "max_count": count,
                "max_uniques": uniques,
                "first_seen": today_str,
                "last_seen": today_str,
            }
        else:
            entry = all_time[path_name]
            entry["title"] = title or entry.get("title", "")
            entry["latest_count"] = count
            entry["latest_uniques"] = uniques
            entry["max_count"] = max(entry.get("max_count", 0), count)
            entry["max_uniques"] = max(entry.get("max_uniques", 0), uniques)
            entry["last_seen"] = today_str

    sorted_all_time = sorted(
        all_time.values(), key=lambda x: x.get("max_count", 0), reverse=True
    )

    return {
        "last_updated": today_str,
        "snapshots": filtered_snapshots,
        "all_time": sorted_all_time,
    }


def fetch_paginated(
    repo: str, resource: str, token: str, accept: str, extra_query: str = ""
) -> list[dict[str, Any]]:
    """Fetch every page of a list endpoint. Any failure aborts the run."""
    records: list[dict[str, Any]] = []
    page = 1

    while True:
        endpoint = (
            f"/repos/{repo}/{resource}?per_page={PER_PAGE}&page={page}{extra_query}"
        )
        data = github_api_get(endpoint, token, accept=accept)

        if not isinstance(data, list):
            raise TrafficCaptureError(
                f"Expected a list from {endpoint}, got {type(data).__name__}"
            )
        records.extend(data)

        if len(data) < PER_PAGE:
            return records
        page += 1


def fetch_all_stargazers(repo: str, token: str) -> list[dict[str, Any]]:
    """Fetch complete list of stargazers with timestamps."""
    raw = fetch_paginated(
        repo, "stargazers", token, accept="application/vnd.github.v3.star+json"
    )
    return [
        {
            "starred_at": item.get("starred_at", ""),
            "date": item.get("starred_at", "")[:10],
            "user": item.get("user", {}).get("login", ""),
        }
        for item in raw
    ]


def fetch_all_forks(repo: str, token: str) -> list[dict[str, Any]]:
    """Fetch complete list of forks with timestamps."""
    raw = fetch_paginated(
        repo,
        "forks",
        token,
        accept="application/vnd.github.v3+json",
        extra_query="&sort=oldest",
    )
    return [
        {
            "created_at": item.get("created_at", ""),
            "date": item.get("created_at", "")[:10],
            "owner": item.get("owner", {}).get("login", ""),
            "html_url": item.get("html_url", ""),
        }
        for item in raw
    ]


def generate_markdown_report(
    summary: dict[str, Any],
    views: list[dict[str, Any]],
    clones: list[dict[str, Any]],
    referrers: dict[str, Any],
    paths: dict[str, Any],
    stargazers: list[dict[str, Any]],
    today: str,
) -> str:
    """Generate Markdown report suitable for rendering directly in GitHub."""
    last_updated = summary.get("last_updated_utc", datetime.now(UTC).isoformat())

    views_7d = window(views, 7, today)
    views_14d = window(views, 14, today)
    clones_7d = window(clones, 7, today)
    clones_14d = window(clones, 14, today)

    def total(items: list[dict[str, Any]], field: str) -> int:
        return sum(int(item.get(field, 0)) for item in items)

    md = [
        f"# 📊 Repository Traffic & Analytics — {summary.get('repository', '')}",
        "",
        "> Long-term historical archive preserving full repository traffic beyond GitHub's default 14-day retention window.",
        "",
        f"**Last Synced:** `{last_updated}`  ",
        f"**Archive Range:** `{summary.get('history_start_date', 'N/A')}` to `{summary.get('history_end_date', 'N/A')}` (`{len(views)}` days recorded)",
        "",
        "## 🚀 High-Level KPI Summary",
        "",
        "| Metric | All-Time Total | Last 14 Days | Last 7 Days |",
        "| :--- | :---: | :---: | :---: |",
        f"| **Page Views** | **{summary.get('all_time_views', 0):,}** | {total(views_14d, 'count'):,} | {total(views_7d, 'count'):,} |",
        f"| **Unique Visitors (summed daily)** | **{summary.get('sum_daily_unique_visitors', 0):,}** | {total(views_14d, 'uniques'):,} | {total(views_7d, 'uniques'):,} |",
        f"| **Git Clones** | **{summary.get('all_time_clones', 0):,}** | {total(clones_14d, 'count'):,} | {total(clones_7d, 'count'):,} |",
        f"| **Unique Cloners (summed daily)** | **{summary.get('sum_daily_unique_cloners', 0):,}** | {total(clones_14d, 'uniques'):,} | {total(clones_7d, 'uniques'):,} |",
        f"| **Stargazers** | **{summary.get('current_stars', 0):,}** | — | — |",
        f"| **Forks** | **{summary.get('current_forks', 0):,}** | — | — |",
        "",
        "> Unique visitors and cloners are summed per day, so someone who visits on three days counts three times.",
        "> GitHub's own 14-day figure deduplicates across the whole window and will read lower.",
        "",
        "---",
        "",
        "## 📈 Recent Views Breakdown (Last 14 Days)",
        "",
        "| Date | Views | Unique Visitors |",
        "| :--- | :---: | :---: |",
    ]

    for v in reversed(views_14d):
        md.append(f"| {v['date']} | {v['count']} | {v['uniques']} |")

    md.extend(
        [
            "",
            "## 📦 Recent Git Clones Breakdown (Last 14 Days)",
            "",
            "| Date | Clones | Unique Cloners |",
            "| :--- | :---: | :---: |",
        ]
    )

    for c in reversed(clones_14d):
        md.append(f"| {c['date']} | {c['count']} | {c['uniques']} |")

    md.extend(
        [
            "",
            "## 🌐 Top Referring Sites (All-Time Tracked)",
            "",
            "| Referrer Domain | Last Recorded | Last Uniques | Peak Count | First Seen | Last Seen |",
            "| :--- | :---: | :---: | :---: | :---: | :---: |",
        ]
    )

    all_time_refs = referrers.get("all_time", [])
    if not all_time_refs:
        md.append("| *No referrers recorded yet* | — | — | — | — | — |")
    else:
        for r in all_time_refs[:TABLE_LIMIT]:
            md.append(
                f"| `{r.get('referrer')}` | {r.get('latest_count', 0)} | {r.get('latest_uniques', 0)} | "
                f"{r.get('max_count', 0)} | {r.get('first_seen', '')} | {r.get('last_seen', '')} |"
            )

    md.extend(
        [
            "",
            "## 📄 Top Content Paths (All-Time Tracked)",
            "",
            "| Path | Title | Last Recorded | Last Uniques | Peak Count | First Seen |",
            "| :--- | :--- | :---: | :---: | :---: | :---: |",
        ]
    )

    all_time_paths = paths.get("all_time", [])
    if not all_time_paths:
        md.append("| *No popular paths recorded yet* | — | — | — | — | — |")
    else:
        for p in all_time_paths[:TABLE_LIMIT]:
            md.append(
                f"| `{p.get('path')}` | {p.get('title', '')} | {p.get('latest_count', 0)} | "
                f"{p.get('latest_uniques', 0)} | {p.get('max_count', 0)} | {p.get('first_seen', '')} |"
            )

    recent_stars = stargazers[-STAR_TABLE_LIMIT:]
    offset = len(stargazers) - len(recent_stars)
    heading = f"## ⭐ Stargazers History\n\nTotal Stars: **{len(stargazers)}**"
    if offset:
        heading += f" — showing the most recent {STAR_TABLE_LIMIT}"

    md.extend(
        [
            "",
            heading,
            "",
            "| Date | User | Cumulative Total |",
            "| :--- | :--- | :---: |",
        ]
    )

    for i, s in enumerate(recent_stars, offset + 1):
        md.append(f"| {s.get('date')} | @{s.get('user')} | {i} |")

    md.extend(
        [
            "",
            "---",
            "",
            "### 💾 Raw Data Access",
            "- [Views JSON](data/views.json) | [Views CSV](data/views.csv)",
            "- [Clones JSON](data/clones.json) | [Clones CSV](data/clones.csv)",
            "- [Referrers JSON](data/referrers.json) | [Referrers CSV](data/referrers.csv)",
            "- [Paths JSON](data/paths.json) | [Paths CSV](data/paths.csv)",
            "- [Stargazers JSON](data/stargazers.json) | [Stargazers CSV](data/stargazers.csv)",
            "- [Forks JSON](data/forks.json) | [Forks CSV](data/forks.csv)",
            "- [Summary JSON](data/summary.json)",
            "",
            "*(Automated archive maintained by `.github/workflows/traffic-analytics.yml`)*",
        ]
    )

    return "\n".join(md) + "\n"


def render_dashboard(
    summary: dict[str, Any],
    views: list[dict[str, Any]],
    clones: list[dict[str, Any]],
    referrers: dict[str, Any],
    paths: dict[str, Any],
    stargazers: list[dict[str, Any]],
    today: str,
) -> str:
    """Fill the dashboard template with one embedded JSON payload.

    The data goes into an `application/json` block rather than executable
    JavaScript, so referrer domains and page titles chosen by third parties are
    never parsed as code. Escaping `</` keeps any such value from closing it.
    """
    payload = {
        "summary": summary,
        "views": views,
        "clones": clones,
        "referrers": referrers.get("all_time", []),
        "paths": paths.get("all_time", []),
        "stars": stargazers,
        "today": today,
    }
    encoded = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.replace(DATA_PLACEHOLDER, encoded)


def capture_traffic(repo: str, output_dir: Path, token: str) -> None:
    """Capture traffic from GitHub API and persist to historical files."""
    data_dir = output_dir / "data"
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    now_iso = datetime.now(UTC).isoformat()

    print(f"[{now_iso}] Capturing repository traffic for {repo}...")

    existing_views = load_json(data_dir / "views.json", default=[])
    existing_clones = load_json(data_dir / "clones.json", default=[])
    existing_referrers = load_json(
        data_dir / "referrers.json", default={"snapshots": [], "all_time": []}
    )
    existing_paths = load_json(
        data_dir / "paths.json", default={"snapshots": [], "all_time": []}
    )
    existing_stars = load_json(data_dir / "stargazers.json", default=[])
    existing_forks = load_json(data_dir / "forks.json", default=[])

    views_api = github_api_get(f"/repos/{repo}/traffic/views", token)
    print(f"✓ Views: {views_api.get('count', 0)} in GitHub's 14-day window")

    clones_api = github_api_get(f"/repos/{repo}/traffic/clones", token)
    print(f"✓ Clones: {clones_api.get('count', 0)} in GitHub's 14-day window")

    referrers_api = github_api_get(f"/repos/{repo}/traffic/popular/referrers", token)
    print(f"✓ Referrers: {len(referrers_api)} domains")

    paths_api = github_api_get(f"/repos/{repo}/traffic/popular/paths", token)
    print(f"✓ Paths: {len(paths_api)} entries")

    stargazers_api = fetch_all_stargazers(repo, token)
    print(f"✓ Stargazers: {len(stargazers_api)} current")

    forks_api = fetch_all_forks(repo, token)
    print(f"✓ Forks: {len(forks_api)} current")

    repo_details = github_api_get(f"/repos/{repo}", token)

    merged_views = merge_time_series(existing_views, views_api.get("views", []))
    merged_clones = merge_time_series(existing_clones, clones_api.get("clones", []))
    merged_referrers = merge_referrers(existing_referrers, referrers_api, today_str)
    merged_paths = merge_paths(existing_paths, paths_api, today_str)
    merged_stars = merge_keyed(existing_stars, stargazers_api, "user", "starred_at")
    merged_forks = merge_keyed(existing_forks, forks_api, "html_url", "created_at")

    summary = {
        "repository": repo,
        "last_updated_utc": now_iso,
        "history_start_date": merged_views[0]["date"] if merged_views else today_str,
        "history_end_date": merged_views[-1]["date"] if merged_views else today_str,
        "total_days_recorded": len(merged_views),
        "all_time_views": sum(v["count"] for v in merged_views),
        "sum_daily_unique_visitors": sum(v["uniques"] for v in merged_views),
        "all_time_clones": sum(c["count"] for c in merged_clones),
        "sum_daily_unique_cloners": sum(c["uniques"] for c in merged_clones),
        "current_stars": repo_details.get("stargazers_count", len(merged_stars)),
        "current_forks": repo_details.get("forks_count", len(merged_forks)),
        "recorded_stars": len(merged_stars),
        "recorded_forks": len(merged_forks),
        "current_watchers": repo_details.get("subscribers_count", 0),
        "open_issues": repo_details.get("open_issues_count", 0),
    }

    save_json(data_dir / "views.json", merged_views)
    save_json(data_dir / "clones.json", merged_clones)
    save_json(data_dir / "referrers.json", merged_referrers)
    save_json(data_dir / "paths.json", merged_paths)
    save_json(data_dir / "stargazers.json", merged_stars)
    save_json(data_dir / "forks.json", merged_forks)
    save_json(data_dir / "summary.json", summary)

    day_fields = ["date", "timestamp", "count", "uniques"]
    stat_fields = [
        "latest_count",
        "latest_uniques",
        "max_count",
        "max_uniques",
        "first_seen",
        "last_seen",
    ]
    save_csv(data_dir / "views.csv", day_fields, merged_views)
    save_csv(data_dir / "clones.csv", day_fields, merged_clones)
    save_csv(
        data_dir / "referrers.csv",
        ["referrer", *stat_fields],
        merged_referrers["all_time"],
    )
    save_csv(
        data_dir / "paths.csv",
        ["path", "title", *stat_fields],
        merged_paths["all_time"],
    )
    save_csv(data_dir / "stargazers.csv", ["starred_at", "date", "user"], merged_stars)
    save_csv(
        data_dir / "forks.csv",
        ["created_at", "date", "owner", "html_url"],
        merged_forks,
    )

    report_args = (
        summary,
        merged_views,
        merged_clones,
        merged_referrers,
        merged_paths,
        merged_stars,
    )
    (output_dir / "README.md").write_text(
        generate_markdown_report(*report_args, today=today_str), encoding="utf-8"
    )
    (output_dir / "index.html").write_text(
        render_dashboard(*report_args, today=today_str), encoding="utf-8"
    )
    # Serve index.html verbatim from GitHub Pages instead of running it through Jekyll.
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")

    print(f"🎉 Archived to {output_dir}")
    print(f"   - Views: {summary['all_time_views']} across {len(merged_views)} days")
    print(f"   - Clones: {summary['all_time_clones']} across {len(merged_clones)} days")
    print(f"   - Referrers: {len(merged_referrers['all_time'])} domains tracked")
    print(f"   - Paths: {len(merged_paths['all_time'])} paths tracked")
    print(
        f"   - Stars: {len(merged_stars)} recorded / {summary['current_stars']} current"
    )
    print(
        f"   - Forks: {len(merged_forks)} recorded / {summary['current_forks']} current"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture and archive GitHub repository traffic statistics."
    )
    parser.add_argument(
        "--repo",
        default=os.getenv("GITHUB_REPOSITORY", "BabakBar/BoringHannover"),
        help="Target repository (owner/name)",
    )
    parser.add_argument(
        "--output-dir",
        default="traffic-data",
        help="Directory to save traffic data and dashboard",
    )
    parser.add_argument("--token", default=None, help="GitHub authentication token")
    args = parser.parse_args()

    try:
        token = require_token(get_auth_token(args.token))
        capture_traffic(args.repo, Path(args.output_dir), token)
    except TrafficCaptureError as err:
        print(f"✗ Traffic capture failed: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
