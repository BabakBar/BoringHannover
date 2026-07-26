"""Tests for City Occasion grouping, lifecycle, and web exports."""

from __future__ import annotations

import json
from datetime import date, datetime

from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import CONFIRMED_TIME
from boringhannover.exporters import export_web_json
from boringhannover.models import Event
from boringhannover.occasions import (
    OccasionDefinition,
    build_occasion_bundles,
    classify_programme_item,
)


def _event(
    *,
    title: str,
    day: int,
    occasion_id: str | None = None,
    venue: str = "Maschsee-Bühne",
) -> Event:
    metadata = {
        "time": "19:00",
        "time_confidence": CONFIRMED_TIME,
        "event_type": "festival" if occasion_id else "concert",
    }
    if occasion_id:
        metadata["occasion_id"] = occasion_id
        metadata["programme_category"] = "Music"

    return Event(
        title=title,
        date=datetime(2026, 7, day, 19, 0, tzinfo=BERLIN_TZ),
        venue=venue,
        url=f"https://example.com/{title.casefold().replace(' ', '-')}",
        category="radar",
        metadata=metadata,
    )


def test_programme_classification_is_conservative_and_ordered() -> None:
    assert classify_programme_item("Familientag mit Live-Musik") == "Family"
    assert classify_programme_item("Open-Air Table Quiz") == "Activities"
    assert classify_programme_item("Poetry Slam und Performance") == "Shows"
    assert classify_programme_item("Party Night mit DJ Lola") == "Party"
    assert classify_programme_item("Irish Folk am Südanleger") == "Music"
    assert classify_programme_item("Weinprobe am See") == "Food & Drink"
    assert classify_programme_item("Ein schöner Abend") is None


def test_build_occasion_bundles_partitions_programme_items() -> None:
    regular = _event(title="Regular Concert", day=27)
    programme = _event(
        title="Maschsee Programme",
        day=28,
        occasion_id="maschseefest-2026",
    )

    regular_events, bundles = build_occasion_bundles(
        [regular, programme],
        now=datetime(2026, 7, 26, 12, 0, tzinfo=BERLIN_TZ),
    )

    assert regular_events == [regular]
    assert len(bundles) == 1
    assert bundles[0].definition.slug == "maschseefest-2026"
    assert bundles[0].status == "happening_now"
    assert bundles[0].events == (programme,)


def test_unknown_occasion_id_fails_open_into_regular_radar() -> None:
    event = _event(title="Unknown Programme", day=28, occasion_id="unknown-2026")

    regular_events, bundles = build_occasion_bundles(
        [event],
        now=datetime(2026, 7, 26, 12, 0, tzinfo=BERLIN_TZ),
    )

    assert regular_events == [event]
    assert bundles[0].events == ()


def test_discovered_occasion_claims_matching_programme_from_regular_sources() -> None:
    discovered = OccasionDefinition(
        id="hannover-festivals:fahrmannsfest-2026",
        slug="fahrmannsfest-2026",
        name="Fährmannsfest 2026",
        kind="festival",
        start_date=date(2026, 7, 31),
        end_date=date(2026, 8, 1),
        location="Justus-Garten-Brücke",
        source_url="https://www.hannover.de/Veranstaltungskalender/Faehrmannsfest",
        description="Alternative music by Leine and Ihme.",
    )
    event = _event(
        title="Fährmannsfest: H-Blockx + Lagwagon",
        day=31,
        venue="Weddigenufer",
    )

    regular_events, bundles = build_occasion_bundles(
        [event],
        occasion_definitions=[discovered],
        now=datetime(2026, 7, 26, 12, 0, tzinfo=BERLIN_TZ),
    )

    faehrmannsfest = next(
        bundle for bundle in bundles if bundle.definition.slug == "fahrmannsfest-2026"
    )
    assert regular_events == []
    assert faehrmannsfest.events == (event,)


def test_first_party_programme_definition_wins_discovery_deduplication() -> None:
    discovered = OccasionDefinition(
        id="hannover-festivals:maschseefest-hannover-2026",
        slug="maschseefest-hannover-2026",
        name="Maschseefest Hannover 2026",
        kind="festival",
        start_date=date(2026, 7, 23),
        end_date=date(2026, 8, 9),
        location="Maschsee",
        source_url="https://www.hannover.de/Veranstaltungskalender/Maschseefest",
        description="Official city calendar summary.",
    )

    _, bundles = build_occasion_bundles(
        [],
        occasion_definitions=[discovered],
        now=datetime(2026, 7, 26, 12, 0, tzinfo=BERLIN_TZ),
    )

    assert [bundle.definition.slug for bundle in bundles] == ["maschseefest-2026"]


def test_web_export_splits_regular_events_and_occasion_programme(tmp_path) -> None:
    regular = _event(title="Regular Concert", day=27, venue="Faust")
    programme = _event(
        title="Maschsee Programme",
        day=28,
        occasion_id="maschseefest-2026",
    )

    export_web_json(
        [],
        [programme, regular],
        tmp_path,
        31,
        2026,
        generated_at=datetime(2026, 7, 26, 12, 0, tzinfo=BERLIN_TZ),
    )

    homepage = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))
    programme_data = json.loads(
        (tmp_path / "occasions" / "maschseefest-2026.json").read_text(encoding="utf-8")
    )

    assert [event["title"] for event in homepage["concerts"]] == ["Regular Concert"]
    assert homepage["concerts"][0]["radarCategory"] == "Live Music"
    assert len(homepage["occasions"]) == 1
    assert homepage["occasions"][0]["programmeCount"] == 1
    assert homepage["occasions"][0]["locationCount"] == 1
    assert homepage["occasions"][0]["preview"][0]["title"] == "Maschsee Programme"
    assert homepage["occasions"][0]["programmePath"] == (
        "occasions/maschseefest-2026.json"
    )

    assert programme_data["occasion"]["slug"] == "maschseefest-2026"
    assert programme_data["programme"][0]["dateISO"] == "2026-07-28"
    assert programme_data["programme"][0]["programmeCategory"] == "Music"
    assert "radarCategory" not in programme_data["programme"][0]


def test_web_export_keeps_summary_when_programme_is_empty(tmp_path) -> None:
    export_web_json(
        [],
        [],
        tmp_path,
        31,
        2026,
        generated_at=datetime(2026, 7, 26, 12, 0, tzinfo=BERLIN_TZ),
    )

    homepage = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))
    programme_data = json.loads(
        (tmp_path / "occasions" / "maschseefest-2026.json").read_text(encoding="utf-8")
    )

    assert homepage["occasions"][0]["programmeCount"] == 0
    assert homepage["occasions"][0]["preview"] == []
    assert programme_data["programme"] == []


def test_web_export_removes_expired_occasion_files(tmp_path) -> None:
    occasions_path = tmp_path / "occasions"
    occasions_path.mkdir()
    stale_path = occasions_path / "old-festival.json"
    stale_path.write_text('{"old": true}', encoding="utf-8")

    export_web_json(
        [],
        [],
        tmp_path,
        40,
        2026,
        generated_at=datetime(2026, 10, 1, 12, 0, tzinfo=BERLIN_TZ),
    )

    assert not stale_path.exists()
    homepage = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))
    assert homepage["occasions"] == []
