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

__all__ = ["should_sync", "sync_to_github"]

logger = logging.getLogger(__name__)

GITHUB_API_BASE: Final[str] = "https://api.github.com"
WEB_EVENTS_REPO_PATH: Final[str] = "web/output/web_events.json"
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

    try:
        return json.dumps(data, sort_keys=True, separators=(",", ":"))
    except Exception:
        return None


def sync_to_github(local_path: str | Path = "output/web_events.json") -> bool:
    """Commit web_events.json to the GitHub repository.

    Uses the GitHub Contents API to create or update the file.
    This triggers the deploy workflow which rebuilds the frontend.

    Args:
        local_path: Path to the local web_events.json file.

    Returns:
        True if sync was successful.

    Raises:
        ValueError: If required environment variables are not set.
    """
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")

    if not token or not repo:
        msg = "GITHUB_TOKEN and GITHUB_REPO must be set for sync"
        raise ValueError(msg)

    local_file = Path(local_path)
    if not local_file.exists():
        logger.error("Local file not found: %s", local_path)
        return False

    content = local_file.read_bytes()
    content_base64 = base64.b64encode(content).decode("ascii")

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
            existing_sha, existing_raw = _get_existing_file(
                client, repo, WEB_EVENTS_REPO_PATH
            )

            if existing_raw is not None:
                existing_norm = _normalize_events_json(existing_raw)
                local_norm = _normalize_events_json(content)
                if (
                    existing_norm is not None
                    and local_norm is not None
                    and existing_norm == local_norm
                ):
                    logger.info(
                        "No meaningful changes detected; skipping GitHub commit"
                    )
                    return True

            payload: dict[str, str] = {
                "message": COMMIT_MESSAGE,
                "content": content_base64,
            }

            if existing_sha:
                payload["sha"] = existing_sha
                logger.info("Updating existing file (sha: %s...)", existing_sha[:7])
            else:
                logger.info("Creating new file in repository")

            response = client.put(
                f"/repos/{repo}/contents/{WEB_EVENTS_REPO_PATH}",
                json=payload,
            )
            response.raise_for_status()

            commit_sha = response.json().get("commit", {}).get("sha", "unknown")
            logger.info("Successfully synced to GitHub (commit: %s)", commit_sha[:7])
            return True

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
