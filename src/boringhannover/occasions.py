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
    "build_occasion_bundles",
    "classify_programme_item",
]

logger = logging.getLogger(__name__)

OccasionStatus = Literal["upcoming", "happening_now", "final_weekend"]


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

    def is_discoverable(self, today: date) -> bool:
        """Return whether this occasion belongs on active product surfaces."""
        visible_from = self.start_date - timedelta(days=self.discovery_lead_days)
        return visible_from <= today <= self.end_date

    def status_on(self, today: date) -> OccasionStatus:
        """Return deterministic lifecycle copy for a discoverable occasion."""
        if today < self.start_date:
            return "upcoming"
        if (self.end_date - today).days <= 2:
            return "final_weekend"
        return "happening_now"


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
            status=definition.status_on(current.date()),
            events=tuple(
                sorted(programme_by_id[occasion_id], key=lambda event: event.date)
            ),
        )
        for occasion_id, definition in definitions.items()
        if definition.is_discoverable(current.date())
    ]
    bundles.sort(
        key=lambda bundle: (bundle.definition.start_date, bundle.definition.name)
    )
    return regular_events, bundles
