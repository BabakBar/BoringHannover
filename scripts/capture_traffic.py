#!/usr/bin/env python3
"""Capture, merge, and visualize GitHub repository traffic for all-time analytics.

Bypasses GitHub's 14-day data retention limit by persistently archiving
daily snapshots of views, clones, referrers, popular content paths,
stargazers, and forks.
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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def get_auth_token(explicit_token: str | None = None) -> str:
    """Resolve GitHub token from arguments, environment, or GitHub CLI."""
    if explicit_token:
        return explicit_token

    for env_var in ("TRAFFIC_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        token = os.getenv(env_var, "").strip()
        if token:
            return token

    # Fallback to `gh auth token`
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )
        token = proc.stdout.strip()
        if token:
            return token
    except Exception:
        pass

    return ""


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
        raise RuntimeError(
            f"GitHub API error {err.code} on {endpoint}: {error_body}"
        ) from err


def load_json(path: Path, default: Any = None) -> Any:
    """Load JSON from file if it exists, otherwise return default."""
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}
    return default if default is not None else {}


def save_json(path: Path, data: Any) -> None:
    """Save data to JSON file with formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    """Save rows to CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def merge_time_series(
    existing_items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
    key_field: str = "timestamp",
    count_fields: tuple[str, ...] = ("count", "uniques"),
) -> list[dict[str, Any]]:
    """Merge time-series data (views or clones) losslessly by date."""
    # Index by YYYY-MM-DD
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


def merge_referrers(
    existing_data: dict[str, Any],
    new_referrers: list[dict[str, Any]],
    today_str: str,
) -> dict[str, Any]:
    """Merge 14-day referrer snapshots and track all-time domain statistics."""
    snapshots = existing_data.get("snapshots", [])
    all_time = {item["referrer"]: item for item in existing_data.get("all_time", [])}

    # Add or update snapshot for today
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

    # Sort all_time by max_count descending
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


def fetch_all_stargazers(repo: str, token: str) -> list[dict[str, Any]]:
    """Fetch complete list of stargazers with timestamps."""
    stargazers: list[dict[str, Any]] = []
    page = 1
    per_page = 100

    while True:
        endpoint = f"/repos/{repo}/stargazers?per_page={per_page}&page={page}"
        try:
            data = github_api_get(
                endpoint,
                token,
                accept="application/vnd.github.v3.star+json",
            )
        except Exception as e:
            print(
                f"Warning: Could not fetch stargazers page {page}: {e}", file=sys.stderr
            )
            break

        if not data or not isinstance(data, list):
            break

        for item in data:
            stargazers.append(
                {
                    "starred_at": item.get("starred_at", ""),
                    "date": item.get("starred_at", "")[:10],
                    "user": item.get("user", {}).get("login", ""),
                }
            )

        if len(data) < per_page:
            break
        page += 1

    return stargazers


def fetch_all_forks(repo: str, token: str) -> list[dict[str, Any]]:
    """Fetch complete list of forks with timestamps."""
    forks: list[dict[str, Any]] = []
    page = 1
    per_page = 100

    while True:
        endpoint = f"/repos/{repo}/forks?per_page={per_page}&page={page}&sort=oldest"
        try:
            data = github_api_get(endpoint, token)
        except Exception as e:
            print(f"Warning: Could not fetch forks page {page}: {e}", file=sys.stderr)
            break

        if not data or not isinstance(data, list):
            break

        for item in data:
            forks.append(
                {
                    "created_at": item.get("created_at", ""),
                    "date": item.get("created_at", "")[:10],
                    "owner": item.get("owner", {}).get("login", ""),
                    "html_url": item.get("html_url", ""),
                }
            )

        if len(data) < per_page:
            break
        page += 1

    return forks


def generate_markdown_report(
    summary: dict[str, Any],
    views: list[dict[str, Any]],
    clones: list[dict[str, Any]],
    referrers: dict[str, Any],
    paths: dict[str, Any],
    stargazers: list[dict[str, Any]],
) -> str:
    """Generate Markdown report suitable for rendering directly in GitHub."""
    last_updated = summary.get("last_updated_utc", datetime.now(UTC).isoformat())

    # Recent slices
    views_7d = views[-7:] if len(views) >= 7 else views
    views_14d = views[-14:] if len(views) >= 14 else views
    clones_7d = clones[-7:] if len(clones) >= 7 else clones
    clones_14d = clones[-14:] if len(clones) >= 14 else clones

    views_7d_total = sum(v["count"] for v in views_7d)
    views_7d_uniques = sum(v["uniques"] for v in views_7d)
    views_14d_total = sum(v["count"] for v in views_14d)
    views_14d_uniques = sum(v["uniques"] for v in views_14d)

    clones_7d_total = sum(c["count"] for c in clones_7d)
    clones_7d_uniques = sum(c["uniques"] for c in clones_7d)
    clones_14d_total = sum(c["count"] for c in clones_14d)
    clones_14d_uniques = sum(c["uniques"] for c in clones_14d)

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
        f"| **Page Views** | **{summary.get('all_time_views', 0):,}** | {views_14d_total:,} | {views_7d_total:,} |",
        f"| **Unique Visitors** | **{summary.get('all_time_unique_visitors', 0):,}** | {views_14d_uniques:,} | {views_7d_uniques:,} |",
        f"| **Git Clones** | **{summary.get('all_time_clones', 0):,}** | {clones_14d_total:,} | {clones_7d_total:,} |",
        f"| **Unique Cloners** | **{summary.get('all_time_unique_cloners', 0):,}** | {clones_14d_uniques:,} | {clones_7d_uniques:,} |",
        f"| **Stargazers** | **{summary.get('current_stars', 0):,}** | — | — |",
        f"| **Forks** | **{summary.get('current_forks', 0):,}** | — | — |",
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
            "| Referrer Domain | Latest Count | Latest Uniques | Peak Count | First Seen | Last Seen |",
            "| :--- | :---: | :---: | :---: | :---: | :---: |",
        ]
    )

    all_time_refs = referrers.get("all_time", [])
    if not all_time_refs:
        md.append("| *No referrers recorded yet* | — | — | — | — | — |")
    else:
        for r in all_time_refs[:15]:
            md.append(
                f"| `{r.get('referrer')}` | {r.get('latest_count', 0)} | {r.get('latest_uniques', 0)} | "
                f"{r.get('max_count', 0)} | {r.get('first_seen', '')} | {r.get('last_seen', '')} |"
            )

    md.extend(
        [
            "",
            "## 📄 Top Content Paths (All-Time Tracked)",
            "",
            "| Path | Title | Latest Count | Latest Uniques | Peak Count | First Seen |",
            "| :--- | :--- | :---: | :---: | :---: | :---: |",
        ]
    )

    all_time_paths = paths.get("all_time", [])
    if not all_time_paths:
        md.append("| *No popular paths recorded yet* | — | — | — | — | — |")
    else:
        for p in all_time_paths[:15]:
            md.append(
                f"| `{p.get('path')}` | {p.get('title', '')} | {p.get('latest_count', 0)} | "
                f"{p.get('latest_uniques', 0)} | {p.get('max_count', 0)} | {p.get('first_seen', '')} |"
            )

    md.extend(
        [
            "",
            "## ⭐ Stargazers History",
            "",
            f"Total Stars: **{len(stargazers)}**",
            "",
            "| Date | User | Cumulative Total |",
            "| :--- | :--- | :---: |",
        ]
    )

    for i, s in enumerate(stargazers, 1):
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
            "- [Summary JSON](data/summary.json)",
            "- [Interactive HTML Dashboard](index.html)",
            "",
            "*(Automated archive maintained by `.github/workflows/traffic-analytics.yml`)*",
        ]
    )

    return "\n".join(md) + "\n"


def generate_interactive_dashboard(
    summary: dict[str, Any],
    views: list[dict[str, Any]],
    clones: list[dict[str, Any]],
    referrers: dict[str, Any],
    paths: dict[str, Any],
    stargazers: list[dict[str, Any]],
) -> str:
    """Generate self-contained, responsive, dark-themed interactive HTML dashboard."""
    repo_name = summary.get("repository", "BoringHannover")
    last_updated = summary.get("last_updated_utc", "")

    views_json_str = json.dumps(views)
    clones_json_str = json.dumps(clones)
    refs_json_str = json.dumps(referrers.get("all_time", []))
    paths_json_str = json.dumps(paths.get("all_time", []))
    stars_json_str = json.dumps(stargazers)
    summary_json_str = json.dumps(summary)

    html = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Analytics Dashboard — {repo_name}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{
        extend: {{
          colors: {{
            gh: {{
              bg: '#0d1117',
              card: '#161b22',
              border: '#30363d',
              header: '#010409',
              text: '#e6edf3',
              muted: '#8b949e',
              blue: '#58a6ff',
              green: '#238636',
              greenLight: '#3fb950',
              purple: '#bc8cff',
              orange: '#f0883e'
            }}
          }}
        }}
      }}
    }}
  </script>
  <style>
    body {{
      background-color: #0d1117;
      color: #e6edf3;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
    }}
    .custom-scrollbar::-webkit-scrollbar {{
      width: 6px;
      height: 6px;
    }}
    .custom-scrollbar::-webkit-scrollbar-thumb {{
      background: #30363d;
      border-radius: 4px;
    }}
  </style>
</head>
<body class="min-h-screen pb-16">
  <!-- Top Navigation / Header -->
  <header class="border-b border-gh-border bg-gh-card/80 backdrop-blur sticky top-0 z-30 px-6 py-4">
    <div class="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <svg class="w-8 h-8 text-white fill-current" viewBox="0 0 16 16">
          <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z"></path>
        </svg>
        <div>
          <h1 class="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            <span>{repo_name}</span>
            <span class="text-xs font-medium px-2 py-0.5 rounded-full bg-gh-border text-gh-blue border border-gh-blue/30">Traffic Analytics</span>
          </h1>
          <p class="text-xs text-gh-muted">Persistent All-Time Traffic Archive &bull; Updated: {last_updated}</p>
        </div>
      </div>

      <!-- Range Selector Filters -->
      <div class="flex items-center gap-2 bg-gh-bg p-1 rounded-lg border border-gh-border text-xs">
        <button onclick="setFilter('7d')" class="range-btn px-3 py-1.5 rounded-md text-gh-muted hover:text-white transition">7D</button>
        <button onclick="setFilter('14d')" class="range-btn px-3 py-1.5 rounded-md text-gh-muted hover:text-white transition">14D</button>
        <button onclick="setFilter('30d')" class="range-btn px-3 py-1.5 rounded-md text-gh-muted hover:text-white transition">30D</button>
        <button onclick="setFilter('90d')" class="range-btn px-3 py-1.5 rounded-md text-gh-muted hover:text-white transition">90D</button>
        <button onclick="setFilter('all')" class="range-btn px-3 py-1.5 rounded-md text-white bg-gh-border font-medium transition">All Time</button>
      </div>
    </div>
  </header>

  <main class="max-w-7xl mx-auto px-6 pt-8 space-y-8">
    <!-- Key Metric Cards -->
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <div class="bg-gh-card border border-gh-border rounded-xl p-4 flex flex-col justify-between">
        <div class="text-xs font-semibold text-gh-muted uppercase tracking-wider">Total Views</div>
        <div class="text-2xl font-extrabold text-gh-blue mt-2" id="kpi-views">{summary.get("all_time_views", 0):,}</div>
        <div class="text-[11px] text-gh-muted mt-1" id="sub-views">All-time count</div>
      </div>

      <div class="bg-gh-card border border-gh-border rounded-xl p-4 flex flex-col justify-between">
        <div class="text-xs font-semibold text-gh-muted uppercase tracking-wider">Unique Visitors</div>
        <div class="text-2xl font-extrabold text-gh-greenLight mt-2" id="kpi-uniques">{summary.get("all_time_unique_visitors", 0):,}</div>
        <div class="text-[11px] text-gh-muted mt-1" id="sub-uniques">Daily unique sum</div>
      </div>

      <div class="bg-gh-card border border-gh-border rounded-xl p-4 flex flex-col justify-between">
        <div class="text-xs font-semibold text-gh-muted uppercase tracking-wider">Git Clones</div>
        <div class="text-2xl font-extrabold text-gh-purple mt-2" id="kpi-clones">{summary.get("all_time_clones", 0):,}</div>
        <div class="text-[11px] text-gh-muted mt-1" id="sub-clones">All-time count</div>
      </div>

      <div class="bg-gh-card border border-gh-border rounded-xl p-4 flex flex-col justify-between">
        <div class="text-xs font-semibold text-gh-muted uppercase tracking-wider">Unique Cloners</div>
        <div class="text-2xl font-extrabold text-gh-orange mt-2" id="kpi-unique-cloners">{summary.get("all_time_unique_cloners", 0):,}</div>
        <div class="text-[11px] text-gh-muted mt-1" id="sub-unique-cloners">Daily unique sum</div>
      </div>

      <div class="bg-gh-card border border-gh-border rounded-xl p-4 flex flex-col justify-between">
        <div class="text-xs font-semibold text-gh-muted uppercase tracking-wider">GitHub Stars</div>
        <div class="text-2xl font-extrabold text-yellow-400 mt-2">{summary.get("current_stars", 0):,}</div>
        <div class="text-[11px] text-gh-muted mt-1">Stargazers</div>
      </div>

      <div class="bg-gh-card border border-gh-border rounded-xl p-4 flex flex-col justify-between">
        <div class="text-xs font-semibold text-gh-muted uppercase tracking-wider">GitHub Forks</div>
        <div class="text-2xl font-extrabold text-slate-300 mt-2">{summary.get("current_forks", 0):,}</div>
        <div class="text-[11px] text-gh-muted mt-1">Forks count</div>
      </div>
    </div>

    <!-- Main Charts Section -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Views Chart -->
      <div class="bg-gh-card border border-gh-border rounded-xl p-5">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-base font-bold text-white flex items-center gap-2">
              <span>Visitors & Page Views</span>
            </h2>
            <p class="text-xs text-gh-muted">Daily page views and unique visitors</p>
          </div>
          <div class="flex items-center gap-2 text-xs">
            <button onclick="toggleScale('views')" id="btn-scale-views" class="px-2.5 py-1 rounded bg-gh-bg border border-gh-border text-gh-muted hover:text-white">Daily</button>
          </div>
        </div>
        <div class="h-72">
          <canvas id="viewsChart"></canvas>
        </div>
      </div>

      <!-- Git Clones Chart -->
      <div class="bg-gh-card border border-gh-border rounded-xl p-5">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-base font-bold text-white flex items-center gap-2">
              <span>Git Clones & Cloners</span>
            </h2>
            <p class="text-xs text-gh-muted">Daily clone operations and unique users</p>
          </div>
          <div class="flex items-center gap-2 text-xs">
            <button onclick="toggleScale('clones')" id="btn-scale-clones" class="px-2.5 py-1 rounded bg-gh-bg border border-gh-border text-gh-muted hover:text-white">Daily</button>
          </div>
        </div>
        <div class="h-72">
          <canvas id="clonesChart"></canvas>
        </div>
      </div>
    </div>

    <!-- Secondary Charts Section -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Cumulative Growth Curve -->
      <div class="bg-gh-card border border-gh-border rounded-xl p-5">
        <div class="mb-4">
          <h2 class="text-base font-bold text-white">Cumulative Growth</h2>
          <p class="text-xs text-gh-muted">Total views vs clones over time</p>
        </div>
        <div class="h-64">
          <canvas id="growthChart"></canvas>
        </div>
      </div>

      <!-- Top Referrers -->
      <div class="bg-gh-card border border-gh-border rounded-xl p-5">
        <div class="mb-4">
          <h2 class="text-base font-bold text-white">Top Referrers</h2>
          <p class="text-xs text-gh-muted">Domains driving traffic to repository</p>
        </div>
        <div class="h-64">
          <canvas id="referrersChart"></canvas>
        </div>
      </div>

      <!-- Star History -->
      <div class="bg-gh-card border border-gh-border rounded-xl p-5">
        <div class="mb-4">
          <h2 class="text-base font-bold text-white">Star History</h2>
          <p class="text-xs text-gh-muted">Stargazer accumulation over time</p>
        </div>
        <div class="h-64">
          <canvas id="starsChart"></canvas>
        </div>
      </div>
    </div>

    <!-- Tables Breakdown -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Popular Paths Table -->
      <div class="bg-gh-card border border-gh-border rounded-xl p-5">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-base font-bold text-white">Popular Content Paths</h2>
          <span class="text-xs text-gh-muted">Tracked Pages</span>
        </div>
        <div class="overflow-x-auto custom-scrollbar max-h-72">
          <table class="w-full text-xs text-left">
            <thead class="text-gh-muted border-b border-gh-border sticky top-0 bg-gh-card">
              <tr>
                <th class="py-2 px-3">Path / Content</th>
                <th class="py-2 px-3 text-right">Latest Views</th>
                <th class="py-2 px-3 text-right">Peak</th>
                <th class="py-2 px-3 text-right">First Seen</th>
              </tr>
            </thead>
            <tbody id="paths-table-body" class="divide-y divide-gh-border/50"></tbody>
          </table>
        </div>
      </div>

      <!-- Referring Domains Table -->
      <div class="bg-gh-card border border-gh-border rounded-xl p-5">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-base font-bold text-white">Referring Domains Breakdown</h2>
          <span class="text-xs text-gh-muted">All Time</span>
        </div>
        <div class="overflow-x-auto custom-scrollbar max-h-72">
          <table class="w-full text-xs text-left">
            <thead class="text-gh-muted border-b border-gh-border sticky top-0 bg-gh-card">
              <tr>
                <th class="py-2 px-3">Referrer Domain</th>
                <th class="py-2 px-3 text-right">Latest Views</th>
                <th class="py-2 px-3 text-right">Latest Uniques</th>
                <th class="py-2 px-3 text-right">Peak Views</th>
                <th class="py-2 px-3 text-right">Last Seen</th>
              </tr>
            </thead>
            <tbody id="referrers-table-body" class="divide-y divide-gh-border/50"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Export Section -->
    <div class="bg-gh-card border border-gh-border rounded-xl p-6 flex flex-col md:flex-row items-center justify-between gap-4">
      <div>
        <h3 class="text-sm font-bold text-white">Export Raw Analytics Data</h3>
        <p class="text-xs text-gh-muted">Download complete historical datasets in standard CSV or JSON format</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <a href="data/views.csv" download class="px-3 py-1.5 rounded-lg bg-gh-bg border border-gh-border text-xs text-white hover:border-gh-blue transition flex items-center gap-1.5">
          <span>📥</span> Views CSV
        </a>
        <a href="data/clones.csv" download class="px-3 py-1.5 rounded-lg bg-gh-bg border border-gh-border text-xs text-white hover:border-gh-purple transition flex items-center gap-1.5">
          <span>📥</span> Clones CSV
        </a>
        <a href="data/referrers.csv" download class="px-3 py-1.5 rounded-lg bg-gh-bg border border-gh-border text-xs text-white hover:border-gh-green transition flex items-center gap-1.5">
          <span>📥</span> Referrers CSV
        </a>
        <a href="data/summary.json" download class="px-3 py-1.5 rounded-lg bg-gh-bg border border-gh-border text-xs text-white hover:border-gh-orange transition flex items-center gap-1.5">
          <span>📄</span> Summary JSON
        </a>
      </div>
    </div>
  </main>

  <script>
    const rawViews = {views_json_str};
    const rawClones = {clones_json_str};
    const rawRefs = {refs_json_str};
    const rawPaths = {paths_json_str};
    const rawStars = {stars_json_str};
    const rawSummary = {summary_json_str};

    let activeFilter = 'all';
    let viewsCumulative = false;
    let clonesCumulative = false;

    let viewsChart, clonesChart, growthChart, referrersChart, starsChart;

    function filterByRange(items) {{
      if (activeFilter === 'all') return items;
      const count = {{ '7d': 7, '14d': 14, '30d': 30, '90d': 90 }}[activeFilter] || items.length;
      return items.slice(-count);
    }}

    function updateKPIs(filteredViews, filteredClones) {{
      const totalViews = filteredViews.reduce((acc, v) => acc + v.count, 0);
      const totalUniques = filteredViews.reduce((acc, v) => acc + v.uniques, 0);
      const totalClones = filteredClones.reduce((acc, c) => acc + c.count, 0);
      const totalUniqueCloners = filteredClones.reduce((acc, c) => acc + c.uniques, 0);

      document.getElementById('kpi-views').innerText = totalViews.toLocaleString();
      document.getElementById('kpi-uniques').innerText = totalUniques.toLocaleString();
      document.getElementById('kpi-clones').innerText = totalClones.toLocaleString();
      document.getElementById('kpi-unique-cloners').innerText = totalUniqueCloners.toLocaleString();

      const label = activeFilter === 'all' ? 'All-time count' : `Last ${{ '7d': '7 days', '14d': '14 days', '30d': '30 days', '90d': '90 days' }}[activeFilter]`;
      document.getElementById('sub-views').innerText = label;
      document.getElementById('sub-uniques').innerText = label;
      document.getElementById('sub-clones').innerText = label;
      document.getElementById('sub-unique-cloners').innerText = label;
    }}

    function renderCharts() {{
      const filteredViews = filterByRange(rawViews);
      const filteredClones = filterByRange(rawClones);
      updateKPIs(filteredViews, filteredClones);

      // Views Chart
      const viewsLabels = filteredViews.map(v => v.date);
      let viewsData = filteredViews.map(v => v.count);
      let uniquesData = filteredViews.map(v => v.uniques);

      if (viewsCumulative) {{
        viewsData = viewsData.map((sum => val => sum += val)(0));
        uniquesData = uniquesData.map((sum => val => sum += val)(0));
      }}

      if (viewsChart) viewsChart.destroy();
      viewsChart = new Chart(document.getElementById('viewsChart'), {{
        type: viewsCumulative ? 'line' : 'bar',
        data: {{
          labels: viewsLabels,
          datasets: [
            {{
              label: 'Total Views',
              data: viewsData,
              backgroundColor: 'rgba(88, 166, 255, 0.65)',
              borderColor: '#58a6ff',
              borderWidth: 2,
              borderRadius: 4,
              fill: viewsCumulative
            }},
            {{
              label: 'Unique Visitors',
              data: uniquesData,
              backgroundColor: 'rgba(63, 185, 80, 0.65)',
              borderColor: '#3fb950',
              borderWidth: 2,
              borderRadius: 4,
              fill: viewsCumulative
            }}
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          interaction: {{ mode: 'index', intersect: false }},
          plugins: {{
            legend: {{ labels: {{ color: '#8b949e', font: {{ size: 11 }} }} }}
          }},
          scales: {{
            x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', maxRotation: 45 }} }},
            y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', precision: 0 }}, beginAtZero: true }}
          }}
        }}
      }});

      // Clones Chart
      const clonesLabels = filteredClones.map(c => c.date);
      let clonesData = filteredClones.map(c => c.count);
      let uniqueClonersData = filteredClones.map(c => c.uniques);

      if (clonesCumulative) {{
        clonesData = clonesData.map((sum => val => sum += val)(0));
        uniqueClonersData = uniqueClonersData.map((sum => val => sum += val)(0));
      }}

      if (clonesChart) clonesChart.destroy();
      clonesChart = new Chart(document.getElementById('clonesChart'), {{
        type: clonesCumulative ? 'line' : 'bar',
        data: {{
          labels: clonesLabels,
          datasets: [
            {{
              label: 'Git Clones',
              data: clonesData,
              backgroundColor: 'rgba(188, 140, 255, 0.65)',
              borderColor: '#bc8cff',
              borderWidth: 2,
              borderRadius: 4,
              fill: clonesCumulative
            }},
            {{
              label: 'Unique Cloners',
              data: uniqueClonersData,
              backgroundColor: 'rgba(240, 136, 62, 0.65)',
              borderColor: '#f0883e',
              borderWidth: 2,
              borderRadius: 4,
              fill: clonesCumulative
            }}
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          interaction: {{ mode: 'index', intersect: false }},
          plugins: {{
            legend: {{ labels: {{ color: '#8b949e', font: {{ size: 11 }} }} }}
          }},
          scales: {{
            x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', maxRotation: 45 }} }},
            y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', precision: 0 }}, beginAtZero: true }}
          }}
        }}
      }});

      // Cumulative Growth Chart
      const growthLabels = rawViews.map(v => v.date);
      let cumViews = rawViews.map(v => v.count).map((sum => val => sum += val)(0));
      let cumClones = rawClones.map(c => c.count).map((sum => val => sum += val)(0));

      if (growthChart) growthChart.destroy();
      growthChart = new Chart(document.getElementById('growthChart'), {{
        type: 'line',
        data: {{
          labels: growthLabels,
          datasets: [
            {{
              label: 'Cumulative Views',
              data: cumViews,
              borderColor: '#58a6ff',
              backgroundColor: 'rgba(88, 166, 255, 0.1)',
              fill: true,
              tension: 0.3
            }},
            {{
              label: 'Cumulative Clones',
              data: cumClones,
              borderColor: '#bc8cff',
              backgroundColor: 'rgba(188, 140, 255, 0.1)',
              fill: true,
              tension: 0.3
            }}
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{ legend: {{ labels: {{ color: '#8b949e', font: {{ size: 11 }} }} }} }},
          scales: {{
            x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }} }},
            y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }}, beginAtZero: true }}
          }}
        }}
      }});

      // Top Referrers Horizontal Bar Chart
      const topRefs = rawRefs.slice(0, 7);
      if (referrersChart) referrersChart.destroy();
      referrersChart = new Chart(document.getElementById('referrersChart'), {{
        type: 'bar',
        data: {{
          labels: topRefs.map(r => r.referrer),
          datasets: [{{
            label: 'Peak Visits',
            data: topRefs.map(r => r.max_count),
            backgroundColor: 'rgba(35, 134, 54, 0.8)',
            borderColor: '#238636',
            borderRadius: 4
          }}]
        }},
        options: {{
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', precision: 0 }} }},
            y: {{ grid: {{ display: false }}, ticks: {{ color: '#e6edf3' }} }}
          }}
        }}
      }});

      // Star History Chart
      const starLabels = rawStars.map(s => s.date);
      const starPoints = rawStars.map((_, idx) => idx + 1);
      if (starsChart) starsChart.destroy();
      starsChart = new Chart(document.getElementById('starsChart'), {{
        type: 'line',
        data: {{
          labels: starLabels,
          datasets: [{{
            label: 'Stars',
            data: starPoints,
            borderColor: '#e3b341',
            backgroundColor: 'rgba(227, 179, 65, 0.15)',
            fill: true,
            stepped: true
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }} }},
            y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', precision: 0 }}, beginAtZero: true }}
          }}
        }}
      }});
    }}

    function populateTables() {{
      const pathsTbody = document.getElementById('paths-table-body');
      pathsTbody.innerHTML = rawPaths.slice(0, 15).map(p => `
        <tr class="hover:bg-gh-bg/50 transition">
          <td class="py-2.5 px-3 font-mono text-gh-blue truncate max-w-xs" title="${{p.path}}">${{p.title || p.path}}</td>
          <td class="py-2.5 px-3 text-right font-medium">${{p.latest_count || 0}}</td>
          <td class="py-2.5 px-3 text-right text-gh-greenLight font-bold">${{p.max_count || 0}}</td>
          <td class="py-2.5 px-3 text-right text-gh-muted">${{p.first_seen || '—'}}</td>
        </tr>
      `).join('');

      const refsTbody = document.getElementById('referrers-table-body');
      refsTbody.innerHTML = rawRefs.slice(0, 15).map(r => `
        <tr class="hover:bg-gh-bg/50 transition">
          <td class="py-2.5 px-3 font-mono text-white">${{r.referrer}}</td>
          <td class="py-2.5 px-3 text-right">${{r.latest_count || 0}}</td>
          <td class="py-2.5 px-3 text-right">${{r.latest_uniques || 0}}</td>
          <td class="py-2.5 px-3 text-right text-gh-greenLight font-bold">${{r.max_count || 0}}</td>
          <td class="py-2.5 px-3 text-right text-gh-muted">${{r.last_seen || '—'}}</td>
        </tr>
      `).join('');
    }}

    function setFilter(filter) {{
      activeFilter = filter;
      document.querySelectorAll('.range-btn').forEach(btn => {{
        if (btn.innerText.toLowerCase() === filter || (filter === 'all' && btn.innerText === 'All Time')) {{
          btn.className = 'range-btn px-3 py-1.5 rounded-md text-white bg-gh-border font-medium transition';
        }} else {{
          btn.className = 'range-btn px-3 py-1.5 rounded-md text-gh-muted hover:text-white transition';
        }}
      }});
      renderCharts();
    }}

    function toggleScale(chartType) {{
      if (chartType === 'views') {{
        viewsCumulative = !viewsCumulative;
        document.getElementById('btn-scale-views').innerText = viewsCumulative ? 'Cumulative' : 'Daily';
      }} else if (chartType === 'clones') {{
        clonesCumulative = !clonesCumulative;
        document.getElementById('btn-scale-clones').innerText = clonesCumulative ? 'Cumulative' : 'Daily';
      }}
      renderCharts();
    }}

    // Initialization
    window.onload = () => {{
      renderCharts();
      populateTables();
    }};
  </script>
</body>
</html>
"""
    return html


def capture_traffic(repo: str, output_dir: Path, token: str) -> None:
    """Capture traffic from GitHub API and persist to historical files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    now_iso = datetime.now(UTC).isoformat()

    print(f"[{now_iso}] Capturing repository traffic for {repo}...")

    # Load existing historical data
    existing_views = load_json(data_dir / "views.json", default=[])
    existing_clones = load_json(data_dir / "clones.json", default=[])
    existing_referrers = load_json(
        data_dir / "referrers.json", default={"snapshots": [], "all_time": []}
    )
    existing_paths = load_json(
        data_dir / "paths.json", default={"snapshots": [], "all_time": []}
    )

    # Fetch Views
    views_api = {}
    try:
        views_api = github_api_get(f"/repos/{repo}/traffic/views", token)
        print(
            f"✓ Fetched views API: {views_api.get('count', 0)} views, {views_api.get('uniques', 0)} uniques in 14-day window"
        )
    except Exception as e:
        print(f"⚠ Failed to fetch views: {e}", file=sys.stderr)

    # Fetch Clones
    clones_api = {}
    try:
        clones_api = github_api_get(f"/repos/{repo}/traffic/clones", token)
        print(
            f"✓ Fetched clones API: {clones_api.get('count', 0)} clones, {clones_api.get('uniques', 0)} uniques in 14-day window"
        )
    except Exception as e:
        print(f"⚠ Failed to fetch clones: {e}", file=sys.stderr)

    # Fetch Referrers
    referrers_api = []
    try:
        referrers_api = github_api_get(
            f"/repos/{repo}/traffic/popular/referrers", token
        )
        print(f"✓ Fetched referrers API: {len(referrers_api)} domains")
    except Exception as e:
        print(f"⚠ Failed to fetch referrers: {e}", file=sys.stderr)

    # Fetch Popular Paths
    paths_api = []
    try:
        paths_api = github_api_get(f"/repos/{repo}/traffic/popular/paths", token)
        print(f"✓ Fetched paths API: {len(paths_api)} paths")
    except Exception as e:
        print(f"⚠ Failed to fetch paths: {e}", file=sys.stderr)

    # Fetch Stargazers
    stargazers = fetch_all_stargazers(repo, token)
    print(f"✓ Fetched stargazers: {len(stargazers)} total stars")

    # Fetch Forks
    forks = fetch_all_forks(repo, token)
    print(f"✓ Fetched forks: {len(forks)} total forks")

    # Fetch Repo Details
    repo_details = {}
    try:
        repo_details = github_api_get(f"/repos/{repo}", token)
    except Exception as e:
        print(f"Warning: Could not fetch repo details: {e}", file=sys.stderr)

    # Lossless Merging
    merged_views = merge_time_series(existing_views, views_api.get("views", []))
    merged_clones = merge_time_series(existing_clones, clones_api.get("clones", []))
    merged_referrers = merge_referrers(existing_referrers, referrers_api, today_str)
    merged_paths = merge_paths(existing_paths, paths_api, today_str)

    # Compute Summary
    all_time_views = sum(v["count"] for v in merged_views)
    all_time_unique_visitors = sum(v["uniques"] for v in merged_views)
    all_time_clones = sum(c["count"] for c in merged_clones)
    all_time_unique_cloners = sum(c["uniques"] for c in merged_clones)

    history_start = merged_views[0]["date"] if merged_views else today_str
    history_end = merged_views[-1]["date"] if merged_views else today_str

    summary = {
        "repository": repo,
        "last_updated_utc": now_iso,
        "history_start_date": history_start,
        "history_end_date": history_end,
        "total_days_recorded": len(merged_views),
        "all_time_views": all_time_views,
        "all_time_unique_visitors": all_time_unique_visitors,
        "all_time_clones": all_time_clones,
        "all_time_unique_cloners": all_time_unique_cloners,
        "current_stars": repo_details.get("stargazers_count", len(stargazers)),
        "current_forks": repo_details.get("forks_count", len(forks)),
        "current_watchers": repo_details.get(
            "subscribers_count", repo_details.get("watchers_count", 0)
        ),
        "open_issues": repo_details.get("open_issues_count", 0),
    }

    # Save JSON files
    save_json(data_dir / "views.json", merged_views)
    save_json(data_dir / "clones.json", merged_clones)
    save_json(data_dir / "referrers.json", merged_referrers)
    save_json(data_dir / "paths.json", merged_paths)
    save_json(data_dir / "stargazers.json", stargazers)
    save_json(data_dir / "forks.json", forks)
    save_json(data_dir / "summary.json", summary)

    # Save CSV files
    save_csv(
        data_dir / "views.csv",
        fieldnames=["date", "timestamp", "count", "uniques"],
        rows=merged_views,
    )
    save_csv(
        data_dir / "clones.csv",
        fieldnames=["date", "timestamp", "count", "uniques"],
        rows=merged_clones,
    )
    save_csv(
        data_dir / "referrers.csv",
        fieldnames=[
            "referrer",
            "latest_count",
            "latest_uniques",
            "max_count",
            "max_uniques",
            "first_seen",
            "last_seen",
        ],
        rows=merged_referrers.get("all_time", []),
    )
    save_csv(
        data_dir / "paths.csv",
        fieldnames=[
            "path",
            "title",
            "latest_count",
            "latest_uniques",
            "max_count",
            "max_uniques",
            "first_seen",
            "last_seen",
        ],
        rows=merged_paths.get("all_time", []),
    )
    save_csv(
        data_dir / "stargazers.csv",
        fieldnames=["starred_at", "date", "user"],
        rows=stargazers,
    )
    save_csv(
        data_dir / "forks.csv",
        fieldnames=["created_at", "date", "owner", "html_url"],
        rows=forks,
    )

    # Save Markdown report
    md_content = generate_markdown_report(
        summary=summary,
        views=merged_views,
        clones=merged_clones,
        referrers=merged_referrers,
        paths=merged_paths,
        stargazers=stargazers,
    )
    with open(output_dir / "README.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    # Save Interactive Dashboard
    html_content = generate_interactive_dashboard(
        summary=summary,
        views=merged_views,
        clones=merged_clones,
        referrers=merged_referrers,
        paths=merged_paths,
        stargazers=stargazers,
    )
    with open(output_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"🎉 Successfully captured and archived all traffic data to: {output_dir}")
    print(f"   - Views: {all_time_views} views across {len(merged_views)} days")
    print(f"   - Clones: {all_time_clones} clones across {len(merged_clones)} days")
    print(
        f"   - Referrers: {len(merged_referrers.get('all_time', []))} domains tracked"
    )
    print(f"   - Popular Paths: {len(merged_paths.get('all_time', []))} paths tracked")
    print(f"   - Stargazers: {len(stargazers)} stars")
    print(f"   - Forks: {len(forks)} forks")


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

    token = get_auth_token(args.token)
    if not token:
        print(
            "Warning: No token found. Unauthenticated requests to GitHub API have strict rate limits and cannot access traffic endpoints.",
            file=sys.stderr,
        )

    capture_traffic(args.repo, Path(args.output_dir), token)


if __name__ == "__main__":
    main()
