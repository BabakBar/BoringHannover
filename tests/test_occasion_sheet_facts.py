"""Official place and entry facts for the occasion detail sheet (#54).

Fixtures are minimized hannover.de detail captures (see HANNOVER_CAPTURES.md).
A fact is exported only when the source states it in a shape we can read
safely; anything else stays unknown instead of being guessed.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from boringhannover.constants import BERLIN_TZ
from boringhannover.exporters import export_web_json
from boringhannover.occasions import Admission, OccasionDefinition, Place
from boringhannover.sources.festivals.hannover_calendar import (
    HannoverFestivalCalendarSource,
)


FIXTURES = Path(__file__).parent / "fixtures"
SOURCE = HannoverFestivalCalendarSource
TIERGARTEN = Place(
    venue="Tiergarten",
    street="Tiergartenstraße 117",
    postal_code="30559",
    locality="Hannover",
)


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _ort(*lines: str) -> str:
    return (
        '<div class="details"><div class="detail-row">'
        '<div class="detail-cell"><p>Ort</p></div>'
        f'<div class="detail-cell"><p>{"<br/>".join(lines)}</p></div>'
        "</div></div>"
    )


def _prices(*rows: tuple[str, str]) -> str:
    cells = "".join(
        '<div class="detail-row">'
        f'<div class="detail-cell"><p>{label}</p></div>'
        f'<div class="detail-cell"><p>{value}</p></div></div>'
        for label, value in rows
    )
    return (
        '<div class="details-table max-w-90 mt-0"><div class="details"></div>'
        f'<div class="table details-table"><div class="details">{cells}</div></div>'
        "</div>"
    )


def _occasion(**overrides: Any) -> OccasionDefinition:
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
    }
    values.update(overrides)
    return OccasionDefinition(**values)


def _summary(tmp_path: Path, definition: OccasionDefinition) -> dict[str, Any]:
    export_web_json(
        [],
        [],
        tmp_path,
        41,
        2026,
        occasion_definitions=[definition],
        generated_at=datetime(2026, 10, 9, 11, 0, tzinfo=BERLIN_TZ),
    )
    manifest = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))
    return manifest["occasions"][0]


# --- Place ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("hannover_festival_detail_tiergartenfest.html", TIERGARTEN),
        (
            "hannover_festival_detail_kiezkultur.html",
            Place(
                street="Zur Bettfedernfabrik 3",
                postal_code="30451",
                locality="Hannover",
            ),
        ),
        (
            "hannover_festival_detail_oktoberfest.html",
            Place(
                venue="Schützenplatz Hannover",
                street="Bruchmeisterallee 1A",
                postal_code="30169",
                locality="Hannover",
            ),
        ),
        (
            "hannover_festival_detail_kunst_kurbis.html",
            Place(
                venue="Eldagser Hoflieferant",
                street="Lange Straße 142",
                postal_code="31832",
                locality="Springe",
            ),
        ),
    ],
)
def test_official_ort_row_becomes_a_postal_address(
    fixture: str,
    expected: Place,
) -> None:
    assert SOURCE._parse_detail_place(_fixture(fixture)) == expected


@pytest.mark.parametrize(
    "lines",
    [
        ("Tiergarten",),
        ("Schützenplatz Hannover", "30169 Hannover"),
        ("Tiergartenstraße 117", "Hannover"),
        ("Tiergartenstraße 117", "3055 Hannover"),
    ],
)
def test_incomplete_address_stays_unknown(lines: tuple[str, ...]) -> None:
    assert SOURCE._parse_detail_place(_ort(*lines)) is None


# --- Entry ------------------------------------------------------------------


def test_price_table_keeps_each_condition_in_source_order() -> None:
    admission = SOURCE._parse_detail_admission(
        _fixture("hannover_festival_detail_tiergartenfest.html")
    )

    # The free tree-slice row is conditional; it must not become "Free".
    assert admission == (
        Admission(
            price="free",
            label="Mit Baumscheibe (für Eichel- und Kastaniensammler*innen)",
        ),
        Admission(price="€3", label="Erwachsene"),
        Admission(price="€2", label="Kinder (bis 14 Jahre)"),
    )


def test_official_free_entry_statement() -> None:
    assert SOURCE._parse_detail_admission(
        _fixture("hannover_festival_detail_kunst_kurbis.html")
    ) == (Admission(price="free"),)


def test_no_price_evidence_means_unknown_entry() -> None:
    assert (
        SOURCE._parse_detail_admission(
            _fixture("hannover_festival_detail_kiezkultur.html")
        )
        == ()
    )


def test_decimal_prices_use_english_notation() -> None:
    assert SOURCE._parse_detail_admission(
        _prices(("Erwachsene", "3,50 €"), ("Familien", "€ 10"))
    ) == (
        Admission(price="€3.50", label="Erwachsene"),
        Admission(price="€10", label="Familien"),
    )


@pytest.mark.parametrize("value", ["ab 5 €", "Spende erbeten", "3 € / 5 €", ""])
def test_one_unreadable_price_makes_the_whole_entry_unknown(value: str) -> None:
    assert (
        SOURCE._parse_detail_admission(
            _prices(("Erwachsene", "3 €"), ("Abendkasse", value))
        )
        == ()
    )


def test_apply_detail_adds_place_and_entry() -> None:
    occasion = SOURCE._apply_detail(
        _occasion(), _fixture("hannover_festival_detail_tiergartenfest.html")
    )

    assert occasion.place == TIERGARTEN
    assert [item.price for item in occasion.admission] == ["free", "€3", "€2"]
    assert occasion.location == "Tiergarten"


# --- Export -----------------------------------------------------------------


def test_export_publishes_place_entry_and_city_area(tmp_path: Path) -> None:
    summary = _summary(
        tmp_path,
        _occasion(
            place=TIERGARTEN,
            admission=(Admission(price="€3", label="Erwachsene"),),
        ),
    )

    assert summary["place"] == {
        "venue": "Tiergarten",
        "street": "Tiergartenstraße 117",
        "postalCode": "30559",
        "locality": "Hannover",
        "municipality": "Hannover",
    }
    assert summary["area"] == "city"
    assert summary["admission"] == [{"label": "Erwachsene", "price": "€3"}]


def test_region_municipality_is_a_day_trip(tmp_path: Path) -> None:
    place = Place(
        venue="Eldagser Hoflieferant",
        street="Lange Straße 142",
        postal_code="31832",
        locality="Springe",
    )
    summary = _summary(
        tmp_path, _occasion(place=place, admission=(Admission(price="free"),))
    )

    assert summary["area"] == "region"
    assert summary["place"]["municipality"] == "Springe"
    assert summary["admission"] == [{"price": "free"}]


@pytest.mark.parametrize("locality", ["Söhlde", "Eldagsen", "Hildesheim"])
def test_unverified_locality_has_no_area(tmp_path: Path, locality: str) -> None:
    place = Place(street="Hauptstraße 1", postal_code="31185", locality=locality)
    summary = _summary(tmp_path, _occasion(place=place))

    assert "area" not in summary
    assert "municipality" not in summary["place"]
    assert summary["place"]["locality"] == locality


def test_unknown_place_and_entry_are_omitted(tmp_path: Path) -> None:
    summary = _summary(tmp_path, _occasion())

    assert {"place", "area", "admission"}.isdisjoint(summary)
