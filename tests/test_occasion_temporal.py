"""Temporal contract for City Occasions (#59): dates, appointments and status."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from boringhannover.constants import BERLIN_TZ
from boringhannover.exporters import export_markdown_digest, export_web_json
from boringhannover.notifier import format_message
from boringhannover.occasions import (
    OccasionDefinition,
    Occurrence,
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


# --- Termine parsing: issue #59 regression strings -------------------------


def test_exclusions_never_become_the_end_of_a_weekday_series() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _detail(
            "<p>04.10.2026 bis 18.10.2026 ab 08:00 bis 17:00 Uhr<br/>sonntags</p>",
            "<strong>Die Veranstaltung findet nicht statt am:</strong>",
            "<p>18.10.2026</p><p>25.10.2026</p>",
        )
    )

    assert schedule is not None
    assert (schedule.start_date, schedule.end_date) == (
        date(2026, 10, 4),
        date(2026, 10, 17),
    )
    assert schedule.confidence == "unknown"
    assert schedule.occurrences == ()
    assert schedule.hours_text == (
        "04.10.2026 bis 18.10.2026 ab 08:00 bis 17:00 Uhr sonntags. "
        "Die Veranstaltung findet nicht statt am: 18.10.2026, 25.10.2026"
    )


def test_exclusion_inside_a_long_series_keeps_the_true_end() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _detail(
            "<p>10.10.2026 bis 12.12.2026 ab 08:00 bis 15:00 Uhr samstags</p>",
            "<p>Die Veranstaltung findet nicht statt am: 31.10.2026</p>",
        )
    )

    assert schedule is not None
    assert (schedule.start_date, schedule.end_date) == (
        date(2026, 10, 10),
        date(2026, 12, 12),
    )
    assert schedule.confidence == "unknown"
    assert schedule.occurrences == ()


def test_separate_evenings_stay_separate_appointments() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _detail(
            "<p>09.10.2026 ab 18:00 Uhr</p><p>10.10.2026 ab 18:00 Uhr</p>",
            "<p>16.10.2026 ab 18:00 Uhr</p><p>17.10.2026 ab 18:00 Uhr</p>",
        )
    )

    assert schedule is not None
    assert (schedule.start_date, schedule.end_date) == (
        date(2026, 10, 9),
        date(2026, 10, 17),
    )
    assert schedule.confidence == "discrete"
    assert schedule.occurrences == tuple(
        Occurrence(date(2026, 10, day), start_time="18:00") for day in (9, 10, 16, 17)
    )
    assert schedule.hours_text == ""


def test_single_appointment_keeps_confirmed_hours() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _detail("<p>10.10.2026 ab 13:00 bis 18:30 Uhr</p>")
    )

    assert schedule is not None
    assert schedule.confidence == "continuous"
    assert schedule.occurrences == (
        Occurrence(date(2026, 10, 10), start_time="13:00", end_time="18:30"),
    )


def test_excluded_day_inside_a_daily_range_is_not_selectable() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _detail(
            "<p>08.10.2026 bis 11.10.2026 ab 15:00 Uhr</p>",
            "<strong>Die Veranstaltung findet nicht statt am:</strong>",
            "<p>09.10.2026</p><p>11.10.2026</p>",
        )
    )

    assert schedule is not None
    assert (schedule.start_date, schedule.end_date) == (
        date(2026, 10, 8),
        date(2026, 10, 10),
    )
    assert schedule.confidence == "discrete"
    assert [occurrence.date for occurrence in schedule.occurrences] == [
        date(2026, 10, 8),
        date(2026, 10, 10),
    ]


@pytest.mark.parametrize(
    "cells",
    [
        ("<p>18.10.2026 bis 04.10.2026</p>",),
        ("<p>31.02.2026 ab 18:00 Uhr</p>",),
        ("<p>10.10.2026 ab 25:00 Uhr</p>",),
        (
            "<p>10.10.2026</p>",
            "<p>Die Veranstaltung findet nicht statt am: 10.10.2026</p>",
        ),
        ("<p>Termine folgen</p>",),
        (
            "<p>10.10.2026 ab 18:00 Uhr</p>",
            "<strong>Entfällt am:</strong>",
            "<p>17.10.2026</p>",
        ),
    ],
)
def test_corrupt_or_empty_schedules_are_rejected(cells: tuple[str, ...]) -> None:
    assert SOURCE._parse_detail_schedule(_detail(*cells)) is None


def test_conflicting_hours_for_one_date_are_ambiguous() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _detail(
            "<p>09.10.2026 bis 10.10.2026 ab 10:00 Uhr</p>",
            "<p>10.10.2026 ab 18:00 Uhr</p>",
        )
    )

    assert schedule is not None
    assert schedule.confidence == "unknown"
    assert schedule.occurrences == ()


def test_overnight_end_time_is_not_invented() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _detail("<p>31.10.2026 ab 21:00 bis 03:00 Uhr</p>")
    )

    assert schedule is not None
    assert schedule.occurrences == (
        Occurrence(date(2026, 10, 31), start_time="21:00"),
    )


def test_reversed_listing_range_is_rejected() -> None:
    assert SOURCE._parse_dates("18.10.2026 bis 04.10.2026") is None
    assert SOURCE._parse_dates("08.10.2026 bis 10.10.2026 und weitere") == (
        date(2026, 10, 8),
        date(2026, 10, 10),
    )


# --- Termine parsing: captured hannover.de pages ---------------------------


def test_captured_faust_flohmarkt_excludes_its_final_sunday() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _fixture("hannover_market_detail_faust_flohmarkt.html")
    )

    assert schedule is not None
    assert (schedule.start_date, schedule.end_date) == (
        date(2026, 10, 11),
        date(2026, 10, 17),
    )
    assert schedule.confidence == "unknown"
    assert "sonntags" in schedule.hours_text
    assert "18.10.2026, 25.10.2026" in schedule.hours_text


def test_captured_neue_bult_keeps_its_december_end() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _fixture("hannover_market_detail_neue_bult.html")
    )

    assert schedule is not None
    assert schedule.end_date == date(2026, 12, 12)


def test_captured_wiesn_lists_twelve_separate_evenings() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _fixture("hannover_festival_detail_wiesn.html")
    )

    assert schedule is not None
    assert schedule.confidence == "discrete"
    assert (schedule.start_date, schedule.end_date) == (
        date(2026, 10, 9),
        date(2026, 11, 7),
    )
    assert len(schedule.occurrences) == 12
    assert Occurrence(date(2026, 11, 1), start_time="11:30") in schedule.occurrences
    assert all(occurrence.end_time is None for occurrence in schedule.occurrences)


def test_captured_oktoberfest_combines_range_and_final_day() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _fixture("hannover_festival_detail_oktoberfest.html")
    )

    assert schedule is not None
    assert schedule.confidence == "continuous"
    assert schedule.occurrences == (
        Occurrence(date(2026, 10, 8), start_time="15:00"),
        Occurrence(date(2026, 10, 9), start_time="15:00"),
        Occurrence(date(2026, 10, 10), start_time="15:00"),
        Occurrence(date(2026, 10, 11), start_time="14:00"),
    )


def test_captured_winterzauber_keeps_per_day_hours() -> None:
    schedule = SOURCE._parse_detail_schedule(
        _fixture("hannover_festival_detail_winterzauber.html")
    )

    assert schedule is not None
    assert schedule.confidence == "continuous"
    assert schedule.occurrences[0] == Occurrence(
        date(2026, 10, 28), start_time="13:00", end_time="20:00"
    )
    assert schedule.occurrences[-1] == Occurrence(
        date(2026, 11, 1), start_time="11:00", end_time="19:00"
    )
    assert len(schedule.occurrences) == 5


def test_captured_tiergartenfest_and_kiezkultur() -> None:
    tiergarten = SOURCE._parse_detail_schedule(
        _fixture("hannover_festival_detail_tiergartenfest.html")
    )
    kiezkultur = SOURCE._parse_detail_schedule(
        _fixture("hannover_festival_detail_kiezkultur.html")
    )

    assert tiergarten is not None
    assert tiergarten.occurrences == (
        Occurrence(date(2026, 10, 10), start_time="13:00", end_time="18:30"),
    )
    assert kiezkultur is not None
    assert kiezkultur.confidence == "continuous"
    assert [occurrence.date for occurrence in kiezkultur.occurrences] == [
        date(2026, 10, 9),
        date(2026, 10, 10),
    ]


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


def test_listing_without_status_marker_has_unknown_status() -> None:
    (occasion,) = SOURCE()._parse_calendar(_card("X-Fest", "10.10.2026"))

    assert occasion.source_status is None
    assert occasion.previous_start_date is None
    assert occasion.name == "X-Fest"


def test_cancellation_is_read_from_the_official_title() -> None:
    (occasion,) = SOURCE()._parse_calendar(
        _card("Abgesagt: X-Fest", "22.10.2026")
    )

    assert occasion.source_status == "cancelled"
    assert occasion.name == "X-Fest"
    assert occasion.slug == "x-fest"


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
    assert occasion.occurrences == (
        Occurrence(date(2026, 10, 22), start_time="19:00"),
    )


def test_postponement_without_new_date_is_postponed() -> None:
    (occasion,) = SOURCE()._parse_calendar(
        _card(
            "Verschoben: X-Fest",
            "15.10.2026",
            "Das Fest wird verschoben, ein neuer Termin steht noch nicht fest.",
        )
    )

    assert occasion.source_status == "postponed"
    assert occasion.previous_start_date is None


def test_dated_rescheduling_keeps_the_original_date() -> None:
    (occasion,) = SOURCE()._parse_calendar(
        _card(
            "Verschoben: X-Fest",
            "12.07.2026",
            "Das Konzert wird vom 30. Juni auf den 12. Juli 2026 verschoben.",
        )
    )

    assert occasion.source_status == "rescheduled"
    assert occasion.start_date == date(2026, 7, 12)
    assert occasion.previous_start_date == date(2026, 6, 30)


def test_rescheduling_across_the_year_boundary() -> None:
    (occasion,) = SOURCE()._parse_calendar(
        _card(
            "Verschoben: X-Fest",
            "06.02.2026",
            "Das Konzert wurde vom 28. November auf den 6. Februar 2026 verschoben.",
        )
    )

    assert occasion.source_status == "rescheduled"
    assert occasion.previous_start_date == date(2025, 11, 28)


def test_rescheduling_to_an_unlisted_date_stays_postponed() -> None:
    (occasion,) = SOURCE()._parse_calendar(
        _card(
            "Verschoben: X-Fest",
            "30.06.2026",
            "Das Konzert wird vom 30.06.2026 auf den 12.07.2026 verschoben.",
        )
    )

    assert occasion.source_status == "postponed"
    assert occasion.previous_start_date is None


def test_rolling_listing_date_is_not_a_rescheduling() -> None:
    (occasion,) = SOURCE()._parse_calendar(
        _card(
            "Oktoberfest 2026",
            "08.10.2026 bis 10.10.2026 und weitere",
            "Vom 25. September bis zum 11. Oktober drehen sich die Karussells.",
        )
    )

    assert occasion.source_status is None
    assert occasion.previous_start_date is None
    assert occasion.start_date == date(2026, 10, 8)


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

    assert occasion_lifecycle(definition, now) == (
        case["expected"]["lifecycle"]  # type: ignore[index]
    )


def test_occurrences_are_limited_to_the_inclusive_horizon() -> None:
    definition = _occasion(
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
    )

    assert [
        occurrence.date
        for occurrence in definition.occurrences_within(date(2026, 12, 25))
    ] == [date(2026, 12, 25), date(2027, 1, 8)]


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

    assert set(summary) == {
        "id",
        "slug",
        "name",
        "kind",
        "startDate",
        "endDate",
        "location",
        "description",
        "imageUrl",
        "sourceUrl",
        "status",
        "programmeCount",
        "locationCount",
        "programmePath",
        "preview",
    }
    assert summary["status"] == "upcoming"


def test_digests_name_source_status_and_sparse_dates(tmp_path: Path) -> None:
    cancelled = _occasion(source_status="cancelled")
    now = datetime(2026, 10, 9, 11, 0, tzinfo=BERLIN_TZ)

    message = format_message(
        {
            "movies_this_week": [],
            "big_events_radar": [],
            "city_occasions": [cancelled, _wiesn()],
        },
        now=now,
    )
    export_markdown_digest(
        [],
        [],
        tmp_path,
        41,
        2026,
        occasion_definitions=[cancelled, _wiesn()],
        generated_at=now,
    )
    markdown = (tmp_path / "weekly_digest.md").read_text(encoding="utf-8")

    assert "Cancelled · 10 Oct-10 Oct" in message
    assert "Selected dates 09 Oct-07 Nov" in message
    assert "**Cancelled** · **10 Oct-10 Oct**" in markdown
    assert "**Selected dates 09 Oct-07 Nov**" in markdown
