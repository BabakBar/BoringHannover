"""Public occasion copy, identity and imagery safety (#60).

Calendar teasers are German, third-party prose and stay internal evidence;
the published description is own English copy or a factual fallback built
only from the source's name and place. Occasion exports carry no
third-party photos.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from boringhannover.constants import BERLIN_TZ
from boringhannover.event_time import CONFIRMED_TIME
from boringhannover.exporters import export_web_json
from boringhannover.models import Event
from boringhannover.occasions import OccasionDefinition


if TYPE_CHECKING:
    from pathlib import Path


NOW = datetime(2026, 10, 9, 11, 0, tzinfo=BERLIN_TZ)
# Listing teaser captured from hannover.de on 9 Oct 2026; the source cuts it.
TIERGARTENFEST_TEASER = (
    "Die Landeshauptstadt Hannover lädt am Samstag (10. Oktober) wieder zum "
    "traditionellen Tiergartenfest ein. Von 13 bis 18:30 Uhr erwartet "
    "Besucher*innen ein..."
)


def _tiergartenfest(**overrides: Any) -> OccasionDefinition:
    values: dict[str, Any] = {
        "id": "hannover-festivals:tiergartenfest-hannover",
        "slug": "tiergartenfest-hannover",
        "name": "Tiergartenfest Hannover",
        "kind": "festival",
        "start_date": date(2026, 10, 10),
        "end_date": date(2026, 10, 10),
        "location": "Tiergarten",
        "source_url": (
            "https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/"
            "Tiergartenfest-Hannover"
        ),
        "description": "",
        "source_summary": TIERGARTENFEST_TEASER,
    }
    values.update(overrides)
    return OccasionDefinition(**values)


def _export(
    tmp_path: Path,
    definitions: list[OccasionDefinition],
    concerts: list[Event] | None = None,
) -> dict[str, Any]:
    export_web_json(
        [],
        concerts or [],
        tmp_path,
        41,
        2026,
        occasion_definitions=definitions,
        generated_at=NOW,
    )
    return json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))


def _event(title: str, *, image_url: str, occasion_id: str | None = None) -> Event:
    metadata: dict[str, str | int | list[str]] = {
        "time": "14:00",
        "time_confidence": CONFIRMED_TIME,
        "event_type": "concert",
        "image_url": image_url,
    }
    if occasion_id:
        metadata["occasion_id"] = occasion_id
    return Event(
        title=title,
        date=datetime(2026, 10, 10, 14, 0, tzinfo=BERLIN_TZ),
        venue="Faust",
        url="https://www.kulturzentrum-faust.de/veranstaltungen/",
        category="radar",
        metadata=metadata,
    )


def test_summary_only_occasion_publishes_factual_english_fallback(
    tmp_path: Path,
) -> None:
    manifest = _export(tmp_path, [_tiergartenfest()])
    (summary,) = manifest["occasions"]

    assert summary["description"] == (
        "Tiergartenfest Hannover at Tiergarten. See the source for details."
    )
    for path in (
        tmp_path / "web_events.json",
        tmp_path / "occasions" / "tiergartenfest-hannover.json",
    ):
        assert "Landeshauptstadt" not in path.read_text(encoding="utf-8")


def test_fallback_omits_an_unknown_place(tmp_path: Path) -> None:
    (summary,) = _export(tmp_path, [_tiergartenfest(location="")])["occasions"]

    assert (
        summary["description"] == "Tiergartenfest Hannover. See the source for details."
    )
    assert "Hannover at" not in summary["description"]


def test_own_english_description_is_published_unchanged(tmp_path: Path) -> None:
    own = "Games, music and food stalls in the Tiergarten."
    (summary,) = _export(tmp_path, [_tiergartenfest(description=own)])["occasions"]

    assert summary["description"] == own


def test_soft_hyphens_leave_display_names_but_not_identity(tmp_path: Path) -> None:
    # As published on 2026-08: the source hyphenates both title and link.
    source_url = (
        "https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/"
        "Fähr­manns­fest-2026"
    )
    definition = _tiergartenfest(
        id="hannover-festivals:fahrmannsfest-2026",
        slug="fahrmannsfest-2026",
        name="Fähr­manns­fest 2026",
        location="Justus-­Garten-Brücke",
        source_url=source_url,
    )

    (summary,) = _export(tmp_path, [definition])["occasions"]

    assert summary["name"] == "Fährmannsfest 2026"
    assert summary["location"] == "Justus-Garten-Brücke"
    assert summary["description"] == (
        "Fährmannsfest 2026 at Justus-Garten-Brücke. See the source for details."
    )
    assert summary["id"] == "hannover-festivals:fahrmannsfest-2026"
    assert summary["slug"] == "fahrmannsfest-2026"
    assert summary["sourceUrl"] == source_url


def test_occasion_exports_carry_no_third_party_images(tmp_path: Path) -> None:
    occasion_id = "hannover-festivals:kiezkultur-festival"
    kiezkultur = _tiergartenfest(
        id=occasion_id,
        slug="kiezkultur-festival",
        name="KiezKultur Festival",
        location="Zur Bettfedernfabrik 3, 30451 Hannover",
        source_url=(
            "https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/"
            "KiezKultur-Festival"
        ),
        source_summary="Faust und Glocksee: zwei Kieze, ein Festival.",
    )
    programme = _event(
        "KiezKultur-Festival 2026",
        image_url="https://www.kulturzentrum-faust.de/media/kiezkultur.jpg",
        occasion_id=occasion_id,
    )
    regular = _event("Regular Concert", image_url="https://example.com/regular.jpg")

    manifest = _export(tmp_path, [kiezkultur], [programme, regular])
    programme_data = json.loads(
        (tmp_path / "occasions" / "kiezkultur-festival.json").read_text(
            encoding="utf-8"
        )
    )
    (summary,) = manifest["occasions"]

    assert "imageUrl" not in summary
    assert "imageUrl" not in programme_data["occasion"]
    assert [item["title"] for item in summary["preview"]] == [
        "KiezKultur-Festival 2026"
    ]
    assert all("imageUrl" not in item for item in summary["preview"])
    assert all("imageUrl" not in item for item in programme_data["programme"])
    # Regular radar events keep their existing image behaviour.
    assert manifest["concerts"][0]["imageUrl"] == "https://example.com/regular.jpg"
