"""City Occasion identity, lifecycle, and programme classification.

Occasions are parent experiences such as Maschseefest. Their programme items
reuse the shared Event model but are kept out of the regular event timeline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from boringhannover.constants import BERLIN_TZ, EVENT_LOOKAHEAD_DAYS


if TYPE_CHECKING:
    from collections.abc import Sequence

    from boringhannover.models import Event

__all__ = [
    "OccasionBundle",
    "OccasionDefinition",
    "OccasionStatus",
    "Occurrence",
    "ScheduleConfidence",
    "SourceStatus",
    "build_occasion_bundles",
    "classify_programme_item",
    "occasion_lifecycle",
]

logger = logging.getLogger(__name__)

OccasionStatus = Literal["upcoming", "happening_now", "final_weekend"]
# continuous: every date of the envelope is a confirmed date; discrete: only
# the listed dates are; unknown: the source schedule could not be parsed safely.
ScheduleConfidence = Literal["continuous", "discrete", "unknown"]
# Explicit source evidence only; a missing status means unknown, not scheduled.
SourceStatus = Literal["scheduled", "cancelled", "postponed", "rescheduled"]


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One confirmed appointment; times are confirmed local HH:MM values."""

    date: date
    start_time: str | None = None
    end_time: str | None = None


@dataclass(frozen=True, slots=True)
class OccasionDefinition:
    """Source-owned identity and lifecycle metadata for a City Occasion."""

    id: str
    slug: str
    name: str
    kind: str
    start_date: date
    end_date: date
    location: str
    source_url: str
    description: str
    discovery_lead_days: int = EVENT_LOOKAHEAD_DAYS
    image_url: str = ""
    occurrences: tuple[Occurrence, ...] = ()
    schedule_confidence: ScheduleConfidence | None = None
    hours_text: str = ""
    source_status: SourceStatus | None = None
    previous_start_date: date | None = None

    def __post_init__(self) -> None:
        """Reject definitions that cannot produce stable public routes."""
        if not self.id or not self.slug or not self.name:
            msg = "Occasion id, slug, and name are required"
            raise ValueError(msg)
        if self.start_date > self.end_date:
            msg = f"Occasion {self.id!r} starts after it ends"
            raise ValueError(msg)
        if not self.source_url.startswith("https://"):
            msg = f"Occasion {self.id!r} requires an HTTPS source URL"
            raise ValueError(msg)
        if any(
            not self.start_date <= occurrence.date <= self.end_date
            for occurrence in self.occurrences
        ):
            msg = f"Occasion {self.id!r} has an occurrence outside its dates"
            raise ValueError(msg)

    def is_discoverable(self, today: date) -> bool:
        """Return whether this occasion belongs on active product surfaces.

        Sparse appointments are discoverable only while one falls inside the
        inclusive horizon; their envelope is not continuous availability.
        """
        if self.schedule_confidence == "discrete":
            return bool(self.occurrences_within(today))
        visible_from = self.start_date - timedelta(days=self.discovery_lead_days)
        return visible_from <= today <= self.end_date

    def occurrences_within(self, today: date) -> tuple[Occurrence, ...]:
        """Return confirmed appointments from today through the horizon.

        The shared EVENT_LOOKAHEAD_DAYS bound applies even when a definition
        allows a longer discovery lead.
        """
        lead = min(self.discovery_lead_days, EVENT_LOOKAHEAD_DAYS)
        horizon_end = today + timedelta(days=lead)
        return tuple(
            occurrence
            for occurrence in self.occurrences
            if today <= occurrence.date <= horizon_end
        )

    def status_on(self, today: date) -> OccasionStatus:
        """Return deterministic lifecycle copy for a discoverable occasion.

        A final weekend is a Saturday or Sunday of a multi-day occasion that
        started before that weekend and ends within it.
        """
        if today < self.start_date:
            return "upcoming"
        if today.weekday() >= 5:
            saturday = today - timedelta(days=today.weekday() - 5)
            sunday = saturday + timedelta(days=1)
            if self.start_date < saturday and self.end_date <= sunday:
                return "final_weekend"
        return "happening_now"


def occasion_lifecycle(
    definition: OccasionDefinition,
    now: datetime,
) -> OccasionStatus | None:
    """Return the lifecycle at the Berlin date of ``now``; None if undiscoverable."""
    today = now.astimezone(BERLIN_TZ).date()
    if not definition.is_discoverable(today):
        return None
    return definition.status_on(today)


@dataclass(frozen=True, slots=True)
class OccasionBundle:
    """A discoverable occasion paired with its current programme items."""

    definition: OccasionDefinition
    status: OccasionStatus
    events: tuple[Event, ...]


_PROGRAMME_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Family",
        (
            "familie",
            "familien",
            "family",
            "kinder",
            "kids",
            "kindertheater",
        ),
    ),
    (
        "Activities",
        (
            "quiz",
            "workshop",
            "yoga",
            "sport",
            "turnier",
            "mitmach",
        ),
    ),
    (
        "Shows",
        (
            "comedy",
            "poetry slam",
            "show",
            "performance",
            "theater",
        ),
    ),
    (
        "Party",
        (
            "after work",
            "afterwork",
            "daydrinking",
            "disco",
            "party",
            "tanzen",
        ),
    ),
    (
        "Music",
        (
            "band",
            "beats",
            "chor",
            "dj",
            "festival",
            "folk",
            "konzert",
            "live",
            "music",
            "musik",
            "sänger",
            "singer",
        ),
    ),
    (
        "Food & Drink",
        (
            "bier",
            "drink",
            "food",
            "happy hour",
            "kulinar",
            "prosecco",
            "wein",
        ),
    ),
)


def classify_programme_item(title: str, description: str = "") -> str | None:
    """Assign a conservative occasion-specific category from source-owned text."""
    searchable = f" {title} {description} ".casefold()
    for category, keywords in _PROGRAMME_CATEGORY_RULES:
        if any(keyword in searchable for keyword in keywords):
            return category
    return None


def _identity_key(name: str) -> str:
    """Normalize an occasion name for cross-source discovery deduplication."""
    without_year = re.sub(r"\b20\d{2}\b", "", name.casefold())
    without_city = without_year.replace("hannover", "")
    return "".join(character for character in without_city if character.isalnum())


def _date_ranges_overlap(
    left: OccasionDefinition,
    right: OccasionDefinition,
) -> bool:
    return left.start_date <= right.end_date and right.start_date <= left.end_date


def _occasion_definitions(
    discovered: Sequence[OccasionDefinition],
) -> dict[str, OccasionDefinition]:
    """Collect occasion definitions from enabled source plugins."""
    from boringhannover.sources import get_all_sources

    definitions: dict[str, OccasionDefinition] = {}
    for source_class in get_all_sources().values():
        if not source_class.enabled:
            continue

        definition = source_class.occasion
        if definition is None:
            continue
        if definition.id in definitions:
            msg = f"Duplicate City Occasion id: {definition.id}"
            raise ValueError(msg)
        definitions[definition.id] = definition

    for definition in discovered:
        if definition.id in definitions:
            continue

        identity = _identity_key(definition.name)
        duplicate = next(
            (
                existing
                for existing in definitions.values()
                if _identity_key(existing.name) == identity
                and _date_ranges_overlap(existing, definition)
            ),
            None,
        )
        if duplicate is not None:
            logger.info(
                "Occasion %r is already covered by %r",
                definition.name,
                duplicate.name,
            )
            continue
        definitions[definition.id] = definition

    return definitions


def build_occasion_bundles(
    events: Sequence[Event],
    *,
    occasion_definitions: Sequence[OccasionDefinition] = (),
    now: datetime | None = None,
) -> tuple[list[Event], list[OccasionBundle]]:
    """Partition regular events and assemble all discoverable City Occasions.

    Definitions come from source plugins, so the exporter and frontend never
    need an event-name allowlist. A discoverable definition is emitted even
    when its programme fetch failed, enabling summary-only degradation.
    """
    current = now.astimezone(BERLIN_TZ) if now is not None else datetime.now(BERLIN_TZ)
    definitions = _occasion_definitions(occasion_definitions)
    programme_by_id: dict[str, list[Event]] = {
        occasion_id: [] for occasion_id in definitions
    }
    regular_events: list[Event] = []

    for event in events:
        raw_occasion_id = event.metadata.get("occasion_id")
        occasion_id = (
            raw_occasion_id.strip() if isinstance(raw_occasion_id, str) else ""
        )
        if not occasion_id:
            matching_definitions = [
                definition
                for definition in definitions.values()
                if (
                    len(identity := _identity_key(definition.name)) >= 7
                    and identity in _identity_key(event.title)
                    and definition.start_date
                    <= event.date.date()
                    <= definition.end_date
                )
            ]
            if len(matching_definitions) == 1:
                programme_by_id[matching_definitions[0].id].append(event)
            else:
                regular_events.append(event)
            continue

        if occasion_id not in definitions:
            logger.warning(
                "Event %r references unknown occasion %r; keeping it in radar",
                event.title,
                occasion_id,
            )
            regular_events.append(event)
            continue

        programme_by_id[occasion_id].append(event)

    bundles = [
        OccasionBundle(
            definition=definition,
            status=status,
            events=tuple(
                sorted(programme_by_id[occasion_id], key=lambda event: event.date)
            ),
        )
        for occasion_id, definition in definitions.items()
        if (status := occasion_lifecycle(definition, current)) is not None
    ]
    bundles.sort(
        key=lambda bundle: (bundle.definition.start_date, bundle.definition.name)
    )
    return regular_events, bundles
