"""Every run is backed up: a real export, packed, must restore without loss."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest

from boringhannover.backup import (
    BackupError,
    backup_run,
    build_snapshot,
    create_client,
    put_verified,
)
from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import CONFIRMED_TIME
from boringhannover.models import Event
from boringhannover.occasions import OccasionDefinition, Occurrence
from boringhannover.output import export_run
from boringhannover.sources.festivals.maschseefest import MaschseefestSource


if TYPE_CHECKING:
    from pathlib import Path


NOW = datetime(2026, 9, 30, 9, 0, 5, tzinfo=UTC)
LONG_DESCRIPTION = "Ein Festival am See mit Musik, Kunst und Essen. " * 8
MOVIE_METADATA = {
    "duration": 124,
    "rating": 16,
    "year": 1975,
    "country": "USA",
    "genres": ["Thriller"],
    "language": "Sprache: Englisch, Untertitel: Deutsch",
    "poster_url": "https://example.com/jaws.jpg",
    "synopsis": "Ein Hai.",
    "trailer_url": "https://example.com/jaws-trailer",
    "cast": [{"role": "Regie", "name": "Steven Spielberg"}],
    "movie_id": 7,
}
CONCERT_METADATA = {
    "event_type": "concert",
    "genre": "Punk / Hardcore",
    "genre_source": "programme_description",
    "description": LONG_DESCRIPTION,
    "image_url": "https://example.com/opening.jpg",
    "end_time": "23:00",
    "price": "16 € zzgl. Geb.",
    "status": "sold_out",
    "address": "Schwarzer Bär 2, 30449 Hannover",
    "programme_category": "Music",
}
# Owned by a registered source rather than discovered this run, e.g. when
# discovery failed: the archive must still carry its definition.
SOURCE_OWNED = MaschseefestSource.occasion
assert SOURCE_OWNED is not None


def _occasion(slug: str, name: str, **overrides: object) -> OccasionDefinition:
    values: dict[str, object] = {
        "id": f"test:{slug}",
        "slug": slug,
        "name": name,
        "kind": "festival",
        "start_date": date(2026, 9, 29),
        "end_date": date(2026, 10, 4),
        "location": "Hannover",
        "source_url": f"https://www.hannover.de/Veranstaltungskalender/{slug}",
        "description": f"{name}.",
    }
    values.update(overrides)
    return OccasionDefinition(**values)  # type: ignore[arg-type]


def _event(title: str, day: int, **metadata: object) -> Event:
    return Event(
        title=title,
        date=datetime(2026, 10, day, 20, 0, tzinfo=BERLIN_TZ),
        venue="Venue",
        url="https://example.com/shared-festival-page",
        category=str(metadata.pop("category", "radar")),  # type: ignore[arg-type]
        metadata={"time": "20:00", "time_confidence": CONFIRMED_TIME, **metadata},
    )


@pytest.fixture
def exported(tmp_path: Path) -> Path:
    """One real export with explicit, inferred and no occasion membership."""
    lakeside = _occasion(
        "lakeside",
        "Lakeside Festival",
        description=LONG_DESCRIPTION,
        occurrences=(Occurrence(date(2026, 10, 1), start_time="18:00"),),
        schedule_confidence="discrete",
    )
    export_run(
        {
            "movies_this_week": [_event("Jaws", 1, category="movie", **MOVIE_METADATA)],
            "big_events_radar": [
                _event(
                    "Opening Concert", 1, occasion_id=lakeside.id, **CONCERT_METADATA
                ),
                _event("Maschsee Night", 2, occasion_id=SOURCE_OWNED.id),
                # No explicit id: claimed by name and date, and shares its
                # URL with other programme items.
                _event("Kiezkultur Festival: Night Market", 2),
                _event("Regular Gig", 3),
            ],
            "city_occasions": [
                lakeside,
                _occasion("kiezkultur", "Kiezkultur Festival"),
                _occasion("quiet-market", "Quiet Market"),
            ],
        },
        tmp_path,
        now=NOW,
    )
    return tmp_path


def _restore(archive: bytes) -> dict[str, bytes]:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        return {
            member.name: tar.extractfile(member).read()  # type: ignore[union-attr]
            for member in tar.getmembers()
        }


def test_restored_snapshot_keeps_every_event_and_occasion_fact(
    exported: Path,
) -> None:
    (exported / "schedule.json").write_text("{}", encoding="utf-8")

    restored = _restore(build_snapshot(exported, NOW).archive)

    # Only this run's files; stray files in the output directory stay out.
    assert sorted(restored) == [
        "archive/2026-W40.json",
        "occasions/kiezkultur.json",
        "occasions/lakeside.json",
        "occasions/quiet-market.json",
        "web_events.json",
    ]
    archive = json.loads(restored["archive/2026-W40.json"])

    (movie,) = archive["movies"]
    assert movie["metadata"] == {
        "time": "20:00",
        "time_confidence": CONFIRMED_TIME,
        **MOVIE_METADATA,
    }

    concerts = {concert["title"]: concert for concert in archive["concerts"]}
    assert concerts["Opening Concert"]["metadata"] == {
        "time": "20:00",
        "time_confidence": CONFIRMED_TIME,
        "occasion_id": "test:lakeside",
        **CONCERT_METADATA,
    }
    assert {title: concert["occasion_id"] for title, concert in concerts.items()} == {
        "Opening Concert": "test:lakeside",
        "Maschsee Night": SOURCE_OWNED.id,
        "Kiezkultur Festival: Night Market": "test:kiezkultur",
        "Regular Gig": None,
    }

    occasions = {occasion["id"]: occasion for occasion in archive["occasions"]}
    assert set(occasions) == {
        "test:lakeside",
        "test:kiezkultur",
        "test:quiet-market",
        SOURCE_OWNED.id,
    }
    assert occasions[SOURCE_OWNED.id]["description"] == SOURCE_OWNED.description
    lakeside = occasions["test:lakeside"]
    # The website summary cuts descriptions to 240 characters; the archive must not.
    assert lakeside["description"] == LONG_DESCRIPTION
    assert len(lakeside["description"]) > 240
    assert lakeside["occurrences"] == [
        {"date": "2026-10-01", "start_time": "18:00", "end_time": None}
    ]
    assert lakeside["schedule_confidence"] == "discrete"
    assert lakeside["source_url"].endswith("/lakeside")


def test_manifest_hashes_match_archive(exported: Path) -> None:
    snapshot = build_snapshot(exported, NOW)
    manifest = json.loads(snapshot.manifest)
    archive = manifest["artifacts"]["archive"]
    members = _restore(snapshot.archive)

    assert archive["sha256"] == hashlib.sha256(snapshot.archive).hexdigest()
    assert archive["size"] == len(snapshot.archive)
    assert archive["key"] == f"{snapshot.prefix}/archive.tar.gz"
    for member in archive["members"]:
        body = members[member["path"]]
        assert member["sha256"] == hashlib.sha256(body).hexdigest()
        assert member["size"] == len(body)
    assert manifest["eventData"] == {"week": 40, "year": 2026}

    digest = hashlib.sha256(snapshot.archive).hexdigest()
    assert snapshot.snapshot_id == f"20260930T090005Z-{digest[:16]}"
    assert snapshot.prefix == f"snapshots/2026/09/{snapshot.snapshot_id}"


def test_archive_is_deterministic(exported: Path) -> None:
    first = build_snapshot(exported, NOW)
    os.utime(exported / "web_events.json", (0, 0))

    assert build_snapshot(exported, NOW).archive == first.archive


@pytest.mark.parametrize("name", ["web_events.json", "archive/2026-W40.json"])
def test_missing_output_file_fails(exported: Path, name: str) -> None:
    (exported / name).unlink()

    with pytest.raises(FileNotFoundError):
        build_snapshot(exported, NOW)


def test_backup_fails_when_not_configured(
    exported: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("R2_BUCKET", raising=False)

    assert backup_run(exported) is False


_R2_CONFIGURED = all(
    os.getenv(key)
    for key in ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
)


@pytest.mark.skipif(not _R2_CONFIGURED, reason="R2 credentials not set")
def test_put_verified_never_overwrites_against_real_bucket() -> None:
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
