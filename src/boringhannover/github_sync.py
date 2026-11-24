"""GitHub sync module for committing data files to trigger frontend rebuilds.

After the backend scrapes event data, this module commits web_events.json
to the repository, which triggers the deploy workflow to rebuild the frontend
with fresh data.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import quote

import httpx

from boringhannover.publication import (
    _decode,
    _get_json,
    _object,
    _rows,
    _sha,
    _text,
    read_published_occasions,
    reconcile_occasions,
)


if TYPE_CHECKING:
    from collections.abc import Sequence

    from boringhannover.models import Event
    from boringhannover.occasions import OccasionDefinition


__all__ = [
    "carry_forward_occasions",
    "remove_unreferenced_programmes",
    "should_sync",
    "sync_to_github",
    "sync_web_data_to_github",
]

logger = logging.getLogger(__name__)

GITHUB_API_BASE: Final[str] = "https://api.github.com"
WEB_EVENTS_REPO_PATH: Final[str] = "web/output/web_events.json"
WEB_OCCASIONS_REPO_DIR: Final[str] = "web/output/occasions"
COMMIT_MESSAGE: Final[str] = "chore: update weekly event data [automated]"
CLEANUP_MESSAGE: Final[str] = (
    "chore: remove unreferenced occasion programmes [automated]"
)


def _github_client() -> httpx.Client:
    return httpx.Client(
        base_url=GITHUB_API_BASE,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )


def carry_forward_occasions(
    output_dir: str | Path,
    *,
    definitions: Sequence[OccasionDefinition],
    now: datetime,
    events: Sequence[Event] = (),
    client: httpx.Client | None = None,
    repo: str | None = None,
) -> list[str]:
    """Validate prior publication before any backup or upload of this candidate."""
    repository = repo or os.environ["GITHUB_REPO"]
    with nullcontext(client) if client is not None else _github_client() as github:
        prior = read_published_occasions(github, repository)
    return reconcile_occasions(
        output_dir, prior, definitions=definitions, now=now, events=events
    )


def should_sync() -> bool:
    """Check if GitHub sync is configured.

    Returns:
        True if GITHUB_TOKEN and GITHUB_REPO are set.
    """
    return bool(os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_REPO"))


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
        with _github_client() as client:
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
    Programmes the published manifest no longer references are removed after it.
    """
    if not _sync_paths(_collect_web_sync_paths(output_dir)):
        return False
    remove_unreferenced_programmes(output_dir)
    return True


def remove_unreferenced_programmes(
    output_dir: str | Path,
    *,
    client: httpx.Client | None = None,
    repo: str | None = None,
) -> bool:
    """Delete published programmes that the published manifest does not reference.

    The Contents API sync only creates and updates files, so programmes of
    expired or re-identified occasions used to stay in the repository forever.
    All removals land in one commit on top of the pinned head, and only when
    that head's manifest is the one this run published: another writer's
    programme-first upload must not lose files its manifest is about to
    reference. The ref update is fast-forward only, so a branch that moved
    meanwhile keeps everything. Publication has already succeeded at this
    point, so any failure only leaves the orphans for the next run.
    """
    repository = repo or os.environ["GITHUB_REPO"]
    output_path = Path(output_dir)
    try:
        with nullcontext(client) if client is not None else _github_client() as github:
            return _remove_unreferenced(github, repository, output_path)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Kept unreferenced programmes: %s", exc)
        return False


def _remove_unreferenced(github: httpx.Client, repo: str, output_path: Path) -> bool:
    prefix = f"/repos/{repo}"
    branch = _text(_get_json(github, prefix), "default_branch")
    head = _get_json(github, f"{prefix}/commits/{quote(branch, safe='')}")
    revision = _sha(head.get("sha"))
    tree_sha = _sha(_object(_object(head.get("commit")).get("tree")).get("sha"))
    listing = _get_json(github, f"{prefix}/git/trees/{tree_sha}", recursive="1")
    if listing.get("truncated") is not False:
        raise ValueError("cannot list the complete publication tree")
    entries = {_text(entry, "path"): entry for entry in _rows(listing.get("tree"))}

    manifest_entry = entries.get(WEB_EVENTS_REPO_PATH)
    if manifest_entry is None:
        raise ValueError("the pinned head has no manifest")
    payload = _get_json(
        github, f"{prefix}/contents/{WEB_EVENTS_REPO_PATH}", ref=revision
    )
    raw = base64.b64decode("".join(_text(payload, "content").split()), validate=True)
    if _git_blob_sha(raw) != manifest_entry.get("sha"):
        raise ValueError("the manifest does not match the pinned tree")
    local_manifest = (output_path / "web_events.json").read_bytes()
    published = _normalize_events_json(raw)
    if published is None or published != _normalize_events_json(local_manifest):
        logger.info("Published manifest is not this run's; kept all programmes")
        return False

    referenced = {
        f"web/output/{_text(summary, 'programmePath')}"
        for summary in _rows(_decode(raw).get("occasions"))
    }
    referenced.update(
        f"{WEB_OCCASIONS_REPO_DIR}/{path.name}"
        for path in (output_path / "occasions").glob("*.json")
    )
    orphans = sorted(
        path
        for path, entry in entries.items()
        if path.startswith(f"{WEB_OCCASIONS_REPO_DIR}/")
        and "/" not in path.removeprefix(f"{WEB_OCCASIONS_REPO_DIR}/")
        and path.endswith(".json")
        and entry.get("type") == "blob"
        and path not in referenced
    )
    if not orphans:
        return True

    new_tree = github.post(
        f"{prefix}/git/trees",
        json={
            "base_tree": tree_sha,
            "tree": [
                {"path": path, "mode": "100644", "type": "blob", "sha": None}
                for path in orphans
            ],
        },
    )
    new_tree.raise_for_status()
    cleanup = github.post(
        f"{prefix}/git/commits",
        json={
            "message": CLEANUP_MESSAGE,
            "tree": _sha(new_tree.json().get("sha")),
            "parents": [revision],
        },
    )
    cleanup.raise_for_status()
    cleanup_sha = _sha(cleanup.json().get("sha"))
    moved = github.patch(
        f"{prefix}/git/refs/heads/{quote(branch)}",
        json={"sha": cleanup_sha, "force": False},
    )
    moved.raise_for_status()
    logger.info(
        "Removed %d unreferenced programmes (commit: %s)",
        len(orphans),
        cleanup_sha[:7],
    )
    return True


def _git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
