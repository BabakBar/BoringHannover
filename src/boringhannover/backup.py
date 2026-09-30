from __future__ import annotations

import gzip
import hashlib
import io
import json
import logging
import os
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


__all__ = [
    "BackupError",
    "Snapshot",
    "backup_run",
    "build_snapshot",
    "create_client",
    "put_verified",
]

logger = logging.getLogger(__name__)

ENV_KEYS: Final = (
    "R2_ENDPOINT",
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
)
# An explicit allow-list: logs, stale files and anything else that happens to
# sit in the output directory must never end up in a snapshot.
TOP_LEVEL_FILES: Final = (
    "concerts.csv",
    "events.json",
    "latest_message.txt",
    "movies.csv",
    "movies_grouped.csv",
    "web_events.json",
    "weekly_digest.md",
)
SCHEMA_VERSION: Final = 1


class BackupError(Exception):
    """A snapshot could not be stored and verified."""


@dataclass(frozen=True)
class Snapshot:
    """One run's packed output, ready to upload."""

    snapshot_id: str
    created_at: datetime
    archive: bytes
    manifest: bytes

    @property
    def prefix(self) -> str:
        return _prefix(self.created_at, self.snapshot_id)


def _prefix(created_at: datetime, snapshot_id: str) -> str:
    return f"snapshots/{created_at:%Y/%m}/{snapshot_id}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _member_paths(output_dir: Path, week: int, year: int) -> list[str]:
    occasions = [
        f"occasions/{path.name}"
        for path in (output_dir / "occasions").glob("*.json")
        if path.is_file() and not path.is_symlink()
    ]
    return sorted([*TOP_LEVEL_FILES, f"archive/{year}-W{week:02d}.json", *occasions])


def _pack(files: dict[str, bytes]) -> bytes:
    """Build a byte-identical tar.gz for identical file contents."""
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path, body in files.items():
            info = tarfile.TarInfo(path)
            info.size = len(body)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(body))
    return gzip.compress(tar_buffer.getvalue(), mtime=0)


def build_snapshot(output_dir: Path, now: datetime) -> Snapshot:
    """Pack the files one run exported into a snapshot.

    Raises:
        FileNotFoundError: If an expected output file is missing.
    """
    meta = json.loads((output_dir / "web_events.json").read_text(encoding="utf-8"))[
        "meta"
    ]
    week, year = int(meta["week"]), int(meta["year"])
    files = {
        path: (output_dir / path).read_bytes()
        for path in _member_paths(output_dir, week, year)
    }

    archive = _pack(files)
    created_at = now.astimezone(UTC)
    snapshot_id = f"{created_at:%Y%m%dT%H%M%SZ}-{_sha256(archive)[:16]}"
    prefix = _prefix(created_at, snapshot_id)
    manifest: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "snapshotId": snapshot_id,
        "prefix": prefix,
        "createdAt": created_at.isoformat().replace("+00:00", "Z"),
        "eventData": {"week": week, "year": year},
        "artifacts": {
            "archive": {
                "key": f"{prefix}/archive.tar.gz",
                "sha256": _sha256(archive),
                "size": len(archive),
                "members": [
                    {"path": path, "sha256": _sha256(body), "size": len(body)}
                    for path, body in files.items()
                ],
            }
        },
    }
    return Snapshot(
        snapshot_id=snapshot_id,
        created_at=created_at,
        archive=archive,
        manifest=json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
    )


def create_client() -> Any:
    """Create an S3 client from the ``R2_*`` environment variables."""
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def put_verified(
    client: Any, bucket: str, key: str, body: bytes, content_type: str
) -> None:
    """Store a new object, then read it back and compare hashes.

    Existing keys are never overwritten, so a stored snapshot is immutable.

    Raises:
        BackupError: If the key exists or the stored copy does not match.
    """
    digest = _sha256(body)
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            Metadata={"sha256": digest},
            IfNoneMatch="*",
        )
        stored = client.get_object(Bucket=bucket, Key=key)["Body"].read()
    except ClientError as err:
        msg = f"Could not store {key}: {err}"
        raise BackupError(msg) from err

    if _sha256(stored) != digest:
        msg = f"Stored copy of {key} does not match what was uploaded"
        raise BackupError(msg)


def backup_run(output_dir: str | Path = "output") -> bool:
    """Upload this run's output as a new snapshot.

    The archive is uploaded before the manifest, so a manifest only exists for
    a snapshot whose archive is complete and verified.

    Returns:
        True if the snapshot is stored and verified.
    """
    missing = [key for key in ENV_KEYS if not os.getenv(key)]
    if missing:
        logger.error("Backup is not configured; missing %s", ", ".join(missing))
        return False

    try:
        snapshot = build_snapshot(Path(output_dir), datetime.now(UTC))
        client = create_client()
        bucket = os.environ["R2_BUCKET"]
        put_verified(
            client,
            bucket,
            f"{snapshot.prefix}/archive.tar.gz",
            snapshot.archive,
            "application/gzip",
        )
        put_verified(
            client,
            bucket,
            f"{snapshot.prefix}/manifest.json",
            snapshot.manifest,
            "application/json",
        )
    except Exception:
        logger.exception("Backup failed")
        return False

    logger.info("Backed up run as snapshot %s", snapshot.snapshot_id)
    return True
