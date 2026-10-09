"""Write one run's output: the web snapshot and the weekly archive."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NotRequired, TypedDict

from boringhannover.constants import BERLIN_TZ
from boringhannover.exporters import archive_weekly_data, export_web_json


if TYPE_CHECKING:
    from boringhannover.models import Event
    from boringhannover.occasions import OccasionDefinition

__all__ = ["EventsData", "export_run"]

logger = logging.getLogger(__name__)


class EventsData(TypedDict):
    """Categorized events from one scrape."""

    movies_this_week: list[Event]
    big_events_radar: list[Event]
    city_occasions: NotRequired[list[OccasionDefinition]]


def export_run(
    events_data: EventsData,
    output_dir: str | Path = "output",
    *,
    now: datetime | None = None,
) -> None:
    """Write web_events.json, the occasion programmes and the weekly archive."""
    current = (now or datetime.now(BERLIN_TZ)).astimezone(BERLIN_TZ)
    year, week, _ = current.isocalendar()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    movies = events_data["movies_this_week"]
    concerts = events_data["big_events_radar"]
    occasions = events_data.get("city_occasions", [])

    export_web_json(
        movies,
        concerts,
        output_path,
        week,
        year,
        occasion_definitions=occasions,
        generated_at=current,
    )
    archive_weekly_data(
        movies,
        concerts,
        output_path,
        week,
        year,
        occasion_definitions=occasions,
        now=current,
    )
    logger.info(
        "Exported %d movies, %d concerts and %d occasions to %s",
        len(movies),
        len(concerts),
        len(occasions),
        output_path,
    )
