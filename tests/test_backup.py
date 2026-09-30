"""Tests for the per-run output backup."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from boringhannover.backup import (
    BackupError,
    backup_run,
    build_snapshot,
    create_client,
    put_verified,
)


NOW = datetime(2026, 9, 30, 9, 0, 5, tzinfo=UTC)
TOP_LEVEL_FILES = (
    "concerts.csv",
    "events.json",
    "latest_message.txt",
    "movies.csv",
    "movies_grouped.csv",
    "weekly_digest.md",
)


def _write_output(root: Path) -> None:
    for name in TOP_LEVEL_FILES:
        (root / name).write_text(f"{name} body", encoding="utf-8")
    (root / "web_events.json").write_text(
        json.dumps({"meta": {"week": 40, "year": 2026}}), encoding="utf-8"
    )
    (root / "archive").mkdir()
    (root / "archive" / "2026-W40.json").write_text("{}", encoding="utf-8")
    (root / "archive" / "2026-W39.json").write_text("{}", encoding="utf-8")
    (root / "occasions").mkdir()
    (root / "occasions" / "oktoberfest.json").write_text("{}", encoding="utf-8")
    (root / "schedule.json").write_text("{}", encoding="utf-8")


def _archive_members(archive: bytes) -> dict[str, bytes]:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        return {
            member.name: tar.extractfile(member).read()  # type: ignore[union-attr]
            for member in tar.getmembers()
        }


def test_snapshot_contains_only_this_runs_files(tmp_path: Path) -> None:
    _write_output(tmp_path)

    snapshot = build_snapshot(tmp_path, NOW)

    assert sorted(_archive_members(snapshot.archive)) == [
        "archive/2026-W40.json",
        "concerts.csv",
        "events.json",
        "latest_message.txt",
        "movies.csv",
        "movies_grouped.csv",
        "occasions/oktoberfest.json",
        "web_events.json",
        "weekly_digest.md",
    ]


def test_manifest_hashes_match_archive(tmp_path: Path) -> None:
    _write_output(tmp_path)

    snapshot = build_snapshot(tmp_path, NOW)
    manifest = json.loads(snapshot.manifest)
    archive = manifest["artifacts"]["archive"]
    members = _archive_members(snapshot.archive)

    assert archive["sha256"] == hashlib.sha256(snapshot.archive).hexdigest()
    assert archive["size"] == len(snapshot.archive)
    assert archive["key"] == f"{snapshot.prefix}/archive.tar.gz"
    for member in archive["members"]:
        body = members[member["path"]]
        assert member["sha256"] == hashlib.sha256(body).hexdigest()
        assert member["size"] == len(body)
    assert manifest["eventData"] == {"week": 40, "year": 2026}
    assert manifest["schemaVersion"] == 1


def test_snapshot_id_and_prefix(tmp_path: Path) -> None:
    _write_output(tmp_path)

    snapshot = build_snapshot(tmp_path, NOW)
    digest = hashlib.sha256(snapshot.archive).hexdigest()

    assert snapshot.snapshot_id == f"20260930T090005Z-{digest[:16]}"
    assert snapshot.prefix == f"snapshots/2026/09/{snapshot.snapshot_id}"


def test_archive_is_deterministic(tmp_path: Path) -> None:
    _write_output(tmp_path)

    first = build_snapshot(tmp_path, NOW)
    os.utime(tmp_path / "events.json", (0, 0))
    second = build_snapshot(tmp_path, NOW)

    assert first.archive == second.archive


def test_missing_output_file_fails(tmp_path: Path) -> None:
    _write_output(tmp_path)
    (tmp_path / "events.json").unlink()

    with pytest.raises(FileNotFoundError):
        build_snapshot(tmp_path, NOW)


def test_backup_fails_when_not_configured(tmp_path: Path, monkeypatch) -> None:
    _write_output(tmp_path)
    monkeypatch.delenv("R2_BUCKET", raising=False)

    assert backup_run(tmp_path) is False


_R2_CONFIGURED = all(
    os.getenv(key)
    for key in ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
)


@pytest.mark.skipif(not _R2_CONFIGURED, reason="R2 credentials not set")
def test_put_verified_against_real_bucket() -> None:
    client = create_client()
    bucket = os.environ["R2_BUCKET"]
    key = f"test/{uuid.uuid4().hex}.txt"
    try:
        put_verified(client, bucket, key, b"backup e2e", "text/plain")
        stored = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        assert stored == b"backup e2e"

        with pytest.raises(BackupError):
            put_verified(client, bucket, key, b"overwrite", "text/plain")
        stored = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        assert stored == b"backup e2e"
    finally:
        client.delete_object(Bucket=bucket, Key=key)
