"""Temporal contract for City Occasions (#59): dates, appointments and status."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

import pytest

from boringhannover.constants import BERLIN_TZ
from boringhannover.exporters import export_web_json
from boringhannover.occasions import (
    OccasionDefinition,
    Occurrence,
    build_occasion_bundles,
    occasion_lifecycle,
)
from boringhannover.sources.festivals.hannover_calendar import (
    HannoverFestivalCalendarSource,
)


FIXTURES = Path(__file__).parent / "fixtures"
CLOCK_CASES = json.loads(
    (FIXTURES / "occasion_clock_cases.json").read_text(encoding="utf-8")
)["cases"]
SOURCE = HannoverFestivalCalendarSource


def _detail(*cells: str, title: str = "", summary: str = "") -> str:
    """Build official detail markup around Termine cell contents."""
    header = ""
    if title:
        header += f'<h1 class="content-detail__title">{title}</h1>'
    if summary:
        header += f'<div class="content-detail__summary"><p>{summary}</p></div>'
    return (
        f'{header}<div class="details"><div class="detail-row">'
        '<div class="detail-cell"><p>Termine</p></div>'
        f'<div class="detail-cell">{"".join(cells)}</div></div></div>'
    )


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _occasion(**overrides: object) -> OccasionDefinition:
    values: dict[str, object] = {
        "id": "hannover-festivals:test-fest",
        "slug": "test-fest",
        "name": "Test Fest",
        "kind": "festival",
        "start_date": date(2026, 10, 10),
        "end_date": date(2026, 10, 10),
        "location": "Tiergarten",
        "source_url": "https://www.hannover.de/Veranstaltungskalender/Test-Fest",
        "description": "Ein Fest.",
    }
    values.update(overrides)
    return OccasionDefinition(**values)  # type: ignore[arg-type]


def _occ(month: int, day: int, start: str | None = None, end: str | None = None):
    return Occurrence(date(2026, month, day), start_time=start, end_time=end)


EXCLUDED = "<strong>Die Veranstaltung findet nicht statt am:</strong>"


# Each case: Termine cells -> (start, end, confidence, occurrences), or None
# when the row must be rejected. Issue #59 regression strings.
@pytest.mark.parametrize(
    ("cells", "expected"),
    [
        pytest.param(
            (
                "<p>04.10.2026 bis 18.10.2026 ab 08:00 bis 17:00 Uhr<br/>sonntags</p>",
                EXCLUDED,
                "<p>18.10.2026</p><p>25.10.2026</p>",
            ),
            (date(2026, 10, 4), date(2026, 10, 18), "unknown", ()),
            id="weekday-series-keeps-source-window-without-guessed-ends",
        ),
        pytest.param(
            (
                "<p>10.10.2026 bis 12.12.2026 ab 08:00 bis 15:00 Uhr samstags</p>",
                "<p>Die Veranstaltung findet nicht statt am: 31.10.2026</p>",
            ),
            (date(2026, 10, 10), date(2026, 12, 12), "unknown", ()),
            id="exclusion-inside-long-series-keeps-true-end",
        ),
        pytest.param(
            (
                "<p>01.10.2026 bis 31.10.2026 ab 11:00 bis 18:00 Uhr dienstags bis sonntags</p>",
                EXCLUDED,
                "<p>31.10.2026</p>",
            ),
            (date(2026, 10, 1), date(2026, 10, 31), "unknown", ()),
            id="excluded-end-of-qualified-range-is-not-guessed",
        ),
        pytest.param(
            (
                "<p>01.10.2026 bis 31.10.2026 dienstags bis sonntags</p>",
                "<p>05.11.2026 ab 18:00 Uhr</p>",
                EXCLUDED,
                "<p>05.11.2026</p>",
            ),
            (date(2026, 10, 1), date(2026, 10, 31), "unknown", ()),
            id="excluded-exact-date-cannot-extend-window",
        ),
        pytest.param(
            (
                "<p>09.10.2026 ab 18:00 Uhr</p><p>10.10.2026 ab 18:00 Uhr</p>",
                "<p>16.10.2026 ab 18:00 Uhr</p><p>17.10.2026 ab 18:00 Uhr</p>",
            ),
            (
                date(2026, 10, 9),
                date(2026, 10, 17),
                "discrete",
                tuple(_occ(10, day, "18:00") for day in (9, 10, 16, 17)),
            ),
            id="separate-evenings-stay-separate",
        ),
        pytest.param(
            ("<p>10.10.2026 ab 13:00 bis 18:30 Uhr</p>",),
            (
                date(2026, 10, 10),
                date(2026, 10, 10),
                "continuous",
                (_occ(10, 10, "13:00", "18:30"),),
            ),
            id="single-appointment-keeps-hours",
        ),
        pytest.param(
            (
                "<p>08.10.2026 bis 11.10.2026 ab 15:00 Uhr</p>",
                EXCLUDED,
                "<p>09.10.2026</p><p>11.10.2026</p>",
            ),
            (
                date(2026, 10, 8),
                date(2026, 10, 10),
                "discrete",
                (_occ(10, 8, "15:00"), _occ(10, 10, "15:00")),
            ),
            id="excluded-days-inside-daily-range-are-not-selectable",
        ),
        pytest.param(
            (
                "<p>09.10.2026 bis 10.10.2026 ab 10:00 Uhr</p>",
                "<p>10.10.2026 ab 18:00 Uhr</p>",
            ),
            (date(2026, 10, 9), date(2026, 10, 10), "unknown", ()),
            id="conflicting-hours-are-ambiguous",
        ),
        pytest.param(
            ("<p>31.10.2026 ab 21:00 bis 03:00 Uhr</p>",),
            (
                date(2026, 10, 31),
                date(2026, 10, 31),
                "continuous",
                (_occ(10, 31, "21:00"),),
            ),
            id="overnight-end-time-is-not-invented",
        ),
        pytest.param(
            ("<p>10.10.2026 ab 13:00 bis 18:30 Uhr</p>", EXCLUDED, "<p>10.10.2026</p>"),
            (date(2026, 10, 10), date(2026, 10, 10), "discrete", ()),
            id="fully-excluded-has-no-appointments",
        ),
        pytest.param(
            (
                "<p>10.10.2026 ab 10:00 Uhr sonntags</p>",
                "<p>Die Veranstaltung findet nicht statt am: 10.10.2026</p>",
            ),
            (date(2026, 10, 10), date(2026, 10, 10), "discrete", ()),
            id="fully-excluded-inline-has-no-appointments",
        ),
        pytest.param(("<p>18.10.2026 bis 04.10.2026</p>",), None, id="reversed-range"),
        pytest.param(("<p>31.02.2026 ab 18:00 Uhr</p>",), None, id="impossible-date"),
        pytest.param(("<p>10.10.2026 ab 25:00 Uhr</p>",), None, id="impossible-hour"),
        pytest.param(("<p>Termine folgen</p>",), None, id="no-dates"),
        pytest.param(
            (
                "<p>10.10.2026 ab 18:00 Uhr</p>",
                "<strong>Entfällt am:</strong>",
                "<p>17.10.2026</p>",
            ),
            None,
            id="unknown-exclusion-label",
        ),
    ],
)
def test_termine_schedule(cells: tuple[str, ...], expected: tuple | None) -> None:
    schedule = SOURCE._parse_detail_schedule(_detail(*cells))

    assert (
        (
            schedule.start_date,
            schedule.end_date,
            schedule.confidence,
            schedule.occurrences,
        )
        if schedule
        else None
    ) == expected


def test_source_hours_text_keeps_series_and_exclusions_verbatim() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _detail(
            "<p>04.10.2026 bis 18.10.2026 ab 08:00 bis 17:00 Uhr<br/>sonntags</p>",
            EXCLUDED,
            "<p>18.10.2026</p><p>25.10.2026</p>",
        )
    )

    assert schedule is not None
    assert schedule.hours_text == (
        "04.10.2026 bis 18.10.2026 ab 08:00 bis 17:00 Uhr sonntags. "
        "Die Veranstaltung findet nicht statt am: 18.10.2026, 25.10.2026"
    )


def test_reversed_listing_range_is_rejected() -> None:
    assert SOURCE._parse_dates("18.10.2026 bis 04.10.2026") is None
    assert SOURCE._parse_dates("08.10.2026 bis 10.10.2026 und weitere") == (
        date(2026, 10, 8),
        date(2026, 10, 10),
    )


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        (
            "hannover_market_detail_faust_flohmarkt.html",
            (date(2026, 10, 11), date(2026, 10, 18), "unknown", ()),
        ),
        (
            "hannover_market_detail_neue_bult.html",
            (date(2026, 10, 10), date(2026, 12, 12), "unknown", ()),
        ),
        (
            "hannover_festival_detail_wiesn.html",
            (
                date(2026, 10, 9),
                date(2026, 11, 7),
                "discrete",
                (
                    *(_occ(10, day, "18:00") for day in (9, 10, 16, 17, 23, 24)),
                    *(_occ(10, day, "18:00") for day in (29, 30, 31)),
                    _occ(11, 1, "11:30"),
                    _occ(11, 6, "18:00"),
                    _occ(11, 7, "18:00"),
                ),
            ),
        ),
        (
            "hannover_festival_detail_oktoberfest.html",
            (
                date(2026, 10, 8),
                date(2026, 10, 11),
                "continuous",
                (
                    _occ(10, 8, "15:00"),
                    _occ(10, 9, "15:00"),
                    _occ(10, 10, "15:00"),
                    _occ(10, 11, "14:00"),
                ),
            ),
        ),
        (
            "hannover_festival_detail_winterzauber.html",
            (
                date(2026, 10, 28),
                date(2026, 11, 1),
                "continuous",
                (
                    _occ(10, 28, "13:00", "20:00"),
                    _occ(10, 29, "11:00", "21:00"),
                    _occ(10, 30, "11:00", "21:00"),
                    _occ(10, 31, "11:00", "21:00"),
                    _occ(11, 1, "11:00", "19:00"),
                ),
            ),
        ),
        (
            "hannover_festival_detail_tiergartenfest.html",
            (
                date(2026, 10, 10),
                date(2026, 10, 10),
                "continuous",
                (_occ(10, 10, "13:00", "18:30"),),
            ),
        ),
        (
            "hannover_festival_detail_kiezkultur.html",
            (
                date(2026, 10, 9),
                date(2026, 10, 10),
                "continuous",
                (_occ(10, 9, "10:00"), _occ(10, 10, "10:00")),
            ),
        ),
    ],
)
def test_captured_detail_pages(fixture: str, expected: tuple) -> None:
    schedule = SOURCE._parse_detail_schedule(_fixture(fixture))

    assert schedule is not None
    assert (
        schedule.start_date,
        schedule.end_date,
        schedule.confidence,
        schedule.occurrences,
    ) == expected


def test_apply_detail_replaces_listing_envelope_with_detail_evidence() -> None:
    listing = _occasion(
        start_date=date(2026, 10, 9),
        end_date=date(2026, 10, 9),
        location="Parkbühne",
    )

    occasion = SOURCE._apply_detail(
        listing, _fixture("hannover_festival_detail_wiesn.html")
    )

    assert (occasion.start_date, occasion.end_date) == (
        date(2026, 10, 9),
        date(2026, 11, 7),
    )
    assert occasion.schedule_confidence == "discrete"
    assert len(occasion.occurrences) == 12
    assert (occasion.id, occasion.slug) == (listing.id, listing.slug)


def test_apply_detail_keeps_listing_dates_when_termine_is_corrupt() -> None:
    listing = _occasion()

    occasion = SOURCE._apply_detail(
        listing, _detail("<p>18.10.2026 bis 04.10.2026</p>")
    )

    assert (occasion.start_date, occasion.end_date) == (
        listing.start_date,
        listing.end_date,
    )
    assert occasion.schedule_confidence is None
    assert occasion.occurrences == ()


def test_fully_excluded_occasion_is_not_published(tmp_path: Path) -> None:
    """An explicitly excluded only date must not fall back to the listing."""
    now = datetime(2026, 10, 10, 12, 0, tzinfo=BERLIN_TZ)
    occasion = SOURCE._apply_detail(
        _occasion(),
        _detail(
            "<p>10.10.2026 ab 13:00 bis 18:30 Uhr</p>",
            "<strong>Die Veranstaltung findet nicht statt am:</strong>",
            "<p>10.10.2026</p>",
        ),
    )

    _, bundles = build_occasion_bundles([], occasion_definitions=[occasion], now=now)
    export_web_json(
        [], [], tmp_path, 41, 2026, occasion_definitions=[occasion], generated_at=now
    )
    homepage = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))

    assert occasion.source_status is None
    assert occasion_lifecycle(occasion, now) is None
    assert [bundle.definition.id for bundle in bundles] == []
    assert homepage["occasions"] == []
    assert not (tmp_path / "occasions" / "test-fest.json").exists()


# --- Source status ----------------------------------------------------------


def _card(title: str, dates: str, description: str = "") -> str:
    return f"""
    <article class="interesting-single line-view-content">
      <h3 class="interesting-single__title">{title}</h3>
      <span class="date__duration">{dates}</span>
      <span class="date__category">Swiss Life Hall</span>
      <div class="interesting-single__description"><p>{description}</p></div>
      <a class="content__read-more" href="/Veranstaltungskalender/Feste-Festivals/X-Fest">mehr</a>
    </article>
    """


# Each case: listing card -> (status, proven previous start date). A
# rescheduling is only "rescheduled" when the original date is proven.
@pytest.mark.parametrize(
    ("title", "dates", "text", "status", "previous"),
    [
        pytest.param("X-Fest", "10.10.2026", "", None, None, id="no-marker"),
        pytest.param(
            "Abgesagt: X-Fest", "22.10.2026", "", "cancelled", None, id="cancelled"
        ),
        pytest.param(
            "Verschoben: X-Fest",
            "15.10.2026",
            "Das Fest wird verschoben, ein neuer Termin steht noch nicht fest.",
            "postponed",
            None,
            id="postponed-without-new-date",
        ),
        pytest.param(
            "Verschoben: X-Fest",
            "12.07.2026",
            "Das Konzert wird vom 30. Juni 2026 auf den 12. Juli 2026 verschoben.",
            "rescheduled",
            date(2026, 6, 30),
            id="rescheduled-later",
        ),
        pytest.param(
            "Verschoben: X-Fest",
            "30.06.2026",
            "Das Konzert wird vom 12.07.2026 auf den 30.06.2026 verschoben.",
            "rescheduled",
            date(2026, 7, 12),
            id="rescheduled-earlier",
        ),
        pytest.param(
            "Verschoben: X-Fest",
            "06.02.2026",
            "Das Konzert wurde vom 28. November 2025 auf den 6. Februar verschoben.",
            "rescheduled",
            date(2025, 11, 28),
            id="rescheduled-across-years",
        ),
        pytest.param(
            "Verschoben: X-Fest",
            "12.07.2026",
            "Das Konzert wird vom 30. Juni auf den 12. Juli 2026 verschoben.",
            "postponed",
            None,
            id="original-year-unproven",
        ),
        pytest.param(
            "Verschoben: X-Fest",
            "30.06.2026",
            "Das Konzert wird vom 12. Juli auf den 30. Juni 2026 verschoben.",
            "postponed",
            None,
            id="original-year-unproven-earlier",
        ),
        pytest.param(
            "Verschoben: X-Fest",
            "06.02.2026",
            "Das Konzert wurde vom 28. November auf den 6. Februar 2026 verschoben.",
            "postponed",
            None,
            id="original-year-unproven-across-years",
        ),
        pytest.param(
            "Verschoben: X-Fest",
            "12.07.2026",
            "Das Konzert wird vom 12.07.2026 auf den 12.07.2026 verschoben.",
            "postponed",
            None,
            id="same-date-is-not-a-rescheduling",
        ),
        pytest.param(
            "Verschoben: X-Fest",
            "30.06.2026",
            "Das Konzert wird vom 30.06.2026 auf den 12.07.2026 verschoben.",
            "postponed",
            None,
            id="new-date-not-the-listed-one",
        ),
        pytest.param(
            "Oktoberfest 2026",
            "08.10.2026 bis 10.10.2026 und weitere",
            "Vom 25. September bis zum 11. Oktober drehen sich die Karussells.",
            None,
            None,
            id="rolling-listing-date-is-not-a-rescheduling",
        ),
    ],
)
def test_listing_source_status(
    title: str, dates: str, text: str, status: str | None, previous: date | None
) -> None:
    (occasion,) = SOURCE()._parse_calendar(_card(title, dates, text))

    assert (occasion.source_status, occasion.previous_start_date) == (
        status,
        previous,
    )
    # The status marker never leaks into the name or slug.
    if title.endswith("X-Fest"):
        assert (occasion.name, occasion.slug) == ("X-Fest", "x-fest")


def test_unknown_month_in_a_rescheduling_fails_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        (occasion,) = SOURCE()._parse_calendar(
            _card(
                "Verschoben: X-Fest",
                "12.07.2026",
                "Das Konzert wird vom 30. Juno 2026 auf den 12. Juli 2026 verschoben.",
            )
        )

    assert occasion.source_status == "postponed"
    assert occasion.previous_start_date is None
    assert "unknown_month_token" in caplog.text


def test_captured_cancelled_detail_page_sets_cancelled() -> None:
    listing = _occasion(
        name="Zum ersten Mal in Hannover: K-Pop Forever",
        start_date=date(2026, 10, 22),
        end_date=date(2026, 10, 22),
    )

    occasion = SOURCE._apply_detail(
        listing, _fixture("hannover_concert_detail_cancelled.html")
    )

    assert occasion.source_status == "cancelled"
    assert occasion.name == "Zum ersten Mal in Hannover: K-Pop Forever"
    assert occasion.start_date == date(2026, 10, 22)
    assert occasion.occurrences == (Occurrence(date(2026, 10, 22), start_time="19:00"),)


# --- Lifecycle and horizon --------------------------------------------------


def _definition_from_case(raw: dict[str, object]) -> OccasionDefinition:
    occurrences = tuple(
        Occurrence(
            date.fromisoformat(str(item["date"])),
            start_time=item.get("startTime"),
            end_time=item.get("endTime"),
        )
        for item in raw.get("occurrences", [])  # type: ignore[union-attr]
    )
    previous = raw.get("previousStartDate")
    return _occasion(
        start_date=date.fromisoformat(str(raw["startDate"])),
        end_date=date.fromisoformat(str(raw["endDate"])),
        occurrences=occurrences,
        schedule_confidence=raw.get("scheduleConfidence"),
        hours_text=raw.get("hoursText", ""),
        source_status=raw.get("sourceStatus"),
        previous_start_date=date.fromisoformat(str(previous)) if previous else None,
    )


@pytest.mark.parametrize("case", CLOCK_CASES, ids=[c["name"] for c in CLOCK_CASES])
def test_shared_clock_fixture_lifecycle(case: dict[str, object]) -> None:
    definition = _definition_from_case(case["occasion"])  # type: ignore[arg-type]
    now = datetime.fromisoformat(str(case["now"]))

    assert (
        occasion_lifecycle(definition, now)
        == (
            case["expected"]["lifecycle"]  # type: ignore[index]
        )
    )


@pytest.mark.parametrize(
    ("definition", "today", "expected"),
    [
        pytest.param(
            _occasion(
                start_date=date(2026, 12, 20),
                end_date=date(2027, 1, 9),
                occurrences=tuple(
                    Occurrence(day)
                    for day in (
                        date(2026, 12, 24),
                        date(2026, 12, 25),
                        date(2027, 1, 8),
                        date(2027, 1, 9),
                    )
                ),
                schedule_confidence="discrete",
            ),
            date(2026, 12, 25),
            [date(2026, 12, 25), date(2027, 1, 8)],
            id="inclusive-horizon",
        ),
        pytest.param(
            _occasion(
                start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 31),
                occurrences=(
                    Occurrence(date(2026, 10, 15)),
                    Occurrence(date(2026, 10, 16)),
                ),
                schedule_confidence="discrete",
                discovery_lead_days=45,
            ),
            date(2026, 10, 1),
            [date(2026, 10, 15)],
            id="discovery-lead-never-widens-the-shared-horizon",
        ),
    ],
)
def test_occurrences_are_limited_to_the_horizon(
    definition: OccasionDefinition, today: date, expected: list[date]
) -> None:
    assert [o.date for o in definition.occurrences_within(today)] == expected


def test_definition_rejects_occurrences_outside_its_envelope() -> None:
    with pytest.raises(ValueError, match="occurrence"):
        _occasion(occurrences=(Occurrence(date(2026, 10, 11)),))


# --- Export and digests -----------------------------------------------------


def _wiesn() -> OccasionDefinition:
    schedule = SOURCE._parse_detail_schedule(
        _fixture("hannover_festival_detail_wiesn.html")
    )
    assert schedule is not None
    return _occasion(
        id="hannover-festivals:hannover-wies-27n",
        slug="hannover-wies-27n",
        name="Hannover Wies'n",
        start_date=schedule.start_date,
        end_date=schedule.end_date,
        occurrences=schedule.occurrences,
        schedule_confidence=schedule.confidence,
        location="Parkbühne",
        source_url="https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/Hannover-Wies%27n",
    )


def test_web_export_adds_horizon_limited_schedule_fields(tmp_path: Path) -> None:
    export_web_json(
        [],
        [],
        tmp_path,
        41,
        2026,
        occasion_definitions=[_wiesn()],
        generated_at=datetime(2026, 10, 9, 11, 0, tzinfo=BERLIN_TZ),
    )

    summary = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))[
        "occasions"
    ][0]
    programme = json.loads(
        (tmp_path / "occasions" / "hannover-wies-27n.json").read_text(encoding="utf-8")
    )

    assert summary["startDate"] == "2026-10-09"
    assert summary["endDate"] == "2026-11-07"
    assert summary["scheduleConfidence"] == "discrete"
    assert summary["occurrences"] == [
        {"date": "2026-10-09", "startTime": "18:00"},
        {"date": "2026-10-10", "startTime": "18:00"},
        {"date": "2026-10-16", "startTime": "18:00"},
        {"date": "2026-10-17", "startTime": "18:00"},
        {"date": "2026-10-23", "startTime": "18:00"},
    ]
    assert "sourceStatus" not in summary
    assert "hoursText" not in summary
    assert programme["occasion"] == summary


def test_web_export_writes_status_and_source_hours(tmp_path: Path) -> None:
    export_web_json(
        [],
        [],
        tmp_path,
        41,
        2026,
        occasion_definitions=[
            _occasion(
                start_date=date(2026, 10, 4),
                end_date=date(2026, 10, 17),
                schedule_confidence="unknown",
                hours_text="04.10.2026 bis 18.10.2026 ab 08:00 bis 17:00 Uhr sonntags",
                source_status="rescheduled",
                previous_start_date=date(2026, 9, 27),
            )
        ],
        generated_at=datetime(2026, 10, 9, 11, 0, tzinfo=BERLIN_TZ),
    )

    summary = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))[
        "occasions"
    ][0]

    assert summary["sourceStatus"] == "rescheduled"
    assert summary["previousStartDate"] == "2026-09-27"
    assert summary["scheduleConfidence"] == "unknown"
    assert summary["hoursText"].endswith("Uhr sonntags")
    assert "occurrences" not in summary


def test_web_export_keeps_legacy_shape_without_schedule_evidence(
    tmp_path: Path,
) -> None:
    export_web_json(
        [],
        [],
        tmp_path,
        41,
        2026,
        occasion_definitions=[_occasion()],
        generated_at=datetime(2026, 10, 9, 11, 0, tzinfo=BERLIN_TZ),
    )

    summary = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))[
        "occasions"
    ][0]

    # imageUrl left the shape in #60: occasions publish no third-party photos.
    assert set(summary) == {
        "id",
        "slug",
        "name",
        "kind",
        "startDate",
        "endDate",
        "location",
        "description",
        "sourceUrl",
        "status",
        "programmeCount",
        "locationCount",
        "programmePath",
        "preview",
    }
    assert summary["status"] == "upcoming"
