"""The send gate: distribution happens after a good data run, never on a clock.

Every hold is reported with a code an operator can act on, and all applicable
holds are reported at once so one fix does not just reveal the next.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from boringhannover.newsletter.content import (
    DEFAULT_CITY_ID,
    DEFAULT_LOCALE,
    EditionContent,
    build_edition_content,
)
from boringhannover.newsletter.ledger import LedgerError, SendLedger


if TYPE_CHECKING:
    from datetime import datetime

__all__ = [
    "MAX_ARTIFACT_AGE_HOURS",
    "GateDecision",
    "GateHold",
    "evaluate_send_gate",
]

logger = logging.getLogger(__name__)

MAX_ARTIFACT_AGE_HOURS: Final[float] = 72.0
"""How old the published artifact may be before an edition is held."""

_OK: Final[str] = "ok"


@dataclass(frozen=True, slots=True)
class GateHold:
    """One reason an edition is not allowed to go out."""

    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class GateDecision:
    """The gate's verdict for one edition."""

    allowed: bool
    holds: tuple[GateHold, ...]
    requires_approval: bool
    content: EditionContent | None

    @property
    def hold_codes(self) -> tuple[str, ...]:
        """Hold codes in the order they were found."""
        return tuple(hold.code for hold in self.holds)


def _load_artifact(path: Path) -> tuple[Mapping[str, Any] | None, GateHold | None]:
    """Read the published artifact, or explain why it is unusable."""
    if not path.exists():
        return None, GateHold(
            "artifact_missing",
            f"No published artifact at {path}; the site would fall back to mock data",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, GateHold("artifact_unreadable", f"Cannot read {path}: {exc}")

    if not isinstance(payload, Mapping):
        return None, GateHold(
            "artifact_unreadable", f"{path} does not contain a JSON object"
        )
    return payload, None


def _health_holds(path: Path | None) -> tuple[list[GateHold], bool]:
    """Check the optional run-health report.

    Returns:
        Holds found, and whether a human must approve the send. Approval is
        required while no health report exists (issue #24 has not landed one).
    """
    if path is None or not path.exists():
        return [], True

    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [
            GateHold("run_unhealthy", f"Cannot read run health report {path}: {exc}")
        ], True

    if not isinstance(report, Mapping):
        return [
            GateHold("run_unhealthy", f"{path} does not contain a JSON object")
        ], True

    failing = [
        str(source.get("name") or "unnamed source")
        for source in report.get("sources") or ()
        if isinstance(source, Mapping) and source.get("status") != _OK
    ]
    overall = str(report.get("status") or "")

    if overall != _OK or failing:
        detail = f"run status {overall or 'unknown'}"
        if failing:
            detail = f"{detail}; unhealthy sources: {', '.join(sorted(failing))}"
        return [GateHold("run_unhealthy", detail)], False

    return [], False


def _ledger_hold(ledger: SendLedger, content: EditionContent) -> GateHold | None:
    """Check whether this edition was already sent or is mid-flight elsewhere."""
    try:
        record = ledger.record_for(content.key)
    except LedgerError as exc:
        return GateHold("ledger_unreadable", str(exc))

    if record is None or record.status == "failed":
        return None

    if record.status == "completed":
        return GateHold(
            "already_sent",
            f"Edition {content.key} was delivered at {record.completed_at}",
        )

    if record.revision != content.revision:
        return GateHold(
            "revision_conflict",
            f"An unfinished send exists for revision {record.revision[:12]}, "
            f"but the current content is revision {content.revision[:12]}",
        )

    return None


def evaluate_send_gate(
    *,
    artifact_path: Path,
    ledger: SendLedger,
    now: datetime,
    health_path: Path | None = None,
    max_artifact_age_hours: float = MAX_ARTIFACT_AGE_HOURS,
    city_id: str = DEFAULT_CITY_ID,
    locale: str = DEFAULT_LOCALE,
) -> GateDecision:
    """Decide whether this week's edition may be sent.

    Args:
        artifact_path: Published ``web_events.json``.
        ledger: Send ledger consulted for duplicate delivery.
        now: Current time, used for the staleness check.
        health_path: Optional run-health report from the scraping run.
        max_artifact_age_hours: Staleness limit for the artifact.
        city_id: City slug for the edition key.
        locale: Edition language.

    Returns:
        The decision, including the edition content when it could be built.
    """
    holds: list[GateHold] = []

    payload, artifact_hold = _load_artifact(artifact_path)
    if artifact_hold is not None:
        holds.append(artifact_hold)

    content: EditionContent | None = None
    if payload is not None:
        try:
            content = build_edition_content(payload, city_id=city_id, locale=locale)
        except ValueError as exc:
            holds.append(GateHold("artifact_unreadable", str(exc)))

    if content is not None:
        age = now - content.generated_at
        if age > timedelta(hours=max_artifact_age_hours):
            holds.append(
                GateHold(
                    "artifact_stale",
                    f"Artifact was generated {age} ago, limit is "
                    f"{max_artifact_age_hours}h",
                )
            )

        if content.is_empty:
            holds.append(
                GateHold(
                    "no_content",
                    "The edition would contain no events at all",
                )
            )

        ledger_hold = _ledger_hold(ledger, content)
        if ledger_hold is not None:
            holds.append(ledger_hold)

    health_hold_list, requires_approval = _health_holds(health_path)
    holds.extend(health_hold_list)

    decision = GateDecision(
        allowed=not holds,
        holds=tuple(holds),
        requires_approval=requires_approval,
        content=content,
    )
    if holds:
        logger.warning(
            "Edition held: %s",
            "; ".join(f"{hold.code} ({hold.detail})" for hold in holds),
        )
    return decision
