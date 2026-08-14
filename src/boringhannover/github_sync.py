"""GitHub sync module for committing data files to trigger frontend rebuilds.

After the backend scrapes event data, this module commits web_events.json
to the repository, which triggers the deploy workflow to rebuild the frontend
with fresh data.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Final

import httpx


__all__ = ["should_sync", "sync_to_github", "sync_web_data_to_github"]

logger = logging.getLogger(__name__)

GITHUB_API_BASE: Final[str] = "https://api.github.com"
WEB_EVENTS_REPO_PATH: Final[str] = "web/output/web_events.json"
WEB_OCCASIONS_REPO_DIR: Final[str] = "web/output/occasions"
COMMIT_MESSAGE: Final[str] = "chore: update weekly event data [automated]"


def should_sync() -> bool:
    """Check if GitHub sync is configured.

    Returns:
        True if GITHUB_TOKEN and GITHUB_REPO are set.
    """
    return bool(os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_REPO"))


def _get_file_sha(client: httpx.Client, repo: str, path: str) -> str | None:
    """Get the SHA of an existing file in the repo.

    Args:
        client: HTTP client with auth headers.
        repo: Repository in owner/repo format.
        path: File path in the repository.

    Returns:
        File SHA if exists, None otherwise.
    """
    try:
        response = client.get(f"/repos/{repo}/contents/{path}")
    except httpx.RequestError:
        return None
    else:
        if response.status_code == 200:
            sha = response.json().get("sha")
            return str(sha) if sha else None
        return None


def _get_existing_file(
    client: httpx.Client,
    repo: str,
    path: str,
) -> tuple[str | None, bytes | None]:
    """Get the current SHA and raw bytes for a file in the repo (if it exists)."""
    try:
        response = client.get(f"/repos/{repo}/contents/{path}")
    except httpx.RequestError:
        return None, None
    else:
        if response.status_code != 200:
            return None, None

        body = response.json()
        sha = body.get("sha")
        content_base64 = body.get("content")
        if not sha or not content_base64:
            return (str(sha) if sha else None), None

        # GitHub may insert newlines into the base64 content.
        try:
            raw = base64.b64decode(str(content_base64).encode("ascii"), validate=False)
        except Exception:
            return str(sha), None
        else:
            return str(sha), raw


def _normalize_events_json(raw: bytes) -> str | None:
    """Normalize JSON for change detection, ignoring volatile metadata fields."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None

    if isinstance(data, dict):
        meta = data.get("meta")
        if isinstance(meta, dict):
            # Avoid commit spam if only the "last updated" timestamp changes.
            meta.pop("updatedAt", None)
            meta.pop("updatedAtISO", None)

    try:
        return json.dumps(data, sort_keys=True, separators=(",", ":"))
    except Exception:
        return None


def _sync_file(
    client: httpx.Client,
    repo: str,
    local_file: Path,
    repo_path: str,
) -> bool:
    """Create or update one generated web-data file."""
    content = local_file.read_bytes()
    existing_sha, existing_raw = _get_existing_file(client, repo, repo_path)

    if existing_raw is not None:
        existing_norm = _normalize_events_json(existing_raw)
        local_norm = _normalize_events_json(content)
        if (
            existing_norm is not None
            and local_norm is not None
            and existing_norm == local_norm
        ):
            logger.info("No meaningful changes for %s; skipping", repo_path)
            return True

    payload: dict[str, str] = {
        "message": COMMIT_MESSAGE,
        "content": base64.b64encode(content).decode("ascii"),
    }
    if existing_sha:
        payload["sha"] = existing_sha

    response = client.put(
        f"/repos/{repo}/contents/{repo_path}",
        json=payload,
    )
    response.raise_for_status()
    commit_sha = response.json().get("commit", {}).get("sha", "unknown")
    logger.info("Synced %s (commit: %s)", repo_path, str(commit_sha)[:7])
    return True


def _sync_paths(paths: list[tuple[Path, str]]) -> bool:
    """Sync generated files in order, leaving the manifest until last."""
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")

    if not token or not repo:
        msg = "GITHUB_TOKEN and GITHUB_REPO must be set for sync"
        raise ValueError(msg)

    missing = [str(local_path) for local_path, _ in paths if not local_path.exists()]
    if missing:
        logger.error("Local files not found: %s", ", ".join(missing))
        return False

    try:
        with httpx.Client(
            base_url=GITHUB_API_BASE,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        ) as client:
            return all(
                _sync_file(client, repo, local_path, repo_path)
                for local_path, repo_path in paths
            )
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "GitHub API error: HTTP %d - %s",
            exc.response.status_code,
            exc.response.text[:200] if exc.response.text else "no details",
        )
        return False
    except httpx.RequestError:
        logger.warning("GitHub sync failed: network error")
        return False


def sync_to_github(local_path: str | Path = "output/web_events.json") -> bool:
    """Commit the web event manifest to the GitHub repository.

    Uses the GitHub Contents API to create or update the file.
    This triggers the deploy workflow which rebuilds the frontend.

    Args:
        local_path: Path to the local web_events.json file.

    Returns:
        True if sync was successful.

    Raises:
        ValueError: If required environment variables are not set.
    """
    local_file = Path(local_path)
    return _sync_paths([(local_file, WEB_EVENTS_REPO_PATH)])


def _collect_web_sync_paths(output_dir: str | Path) -> list[tuple[Path, str]]:
    """Collect programme files first and the homepage manifest last."""
    output_path = Path(output_dir)
    occasion_paths = sorted((output_path / "occasions").glob("*.json"))
    paths = [
        (
            occasion_path,
            f"{WEB_OCCASIONS_REPO_DIR}/{occasion_path.name}",
        )
        for occasion_path in occasion_paths
    ]
    paths.append((output_path / "web_events.json", WEB_EVENTS_REPO_PATH))
    return paths


def sync_web_data_to_github(output_dir: str | Path = "output") -> bool:
    """Sync occasion programmes before the manifest that references them.

    Each changed file uses a Contents API commit. The manifest is deliberately
    last so a failed programme upload cannot publish a broken frontend contract.
    Deploy concurrency collapses these generated commits into the latest build.
    """
    return _sync_paths(_collect_web_sync_paths(output_dir))
