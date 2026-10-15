"""What each source operation in one run actually produced.

A count alone cannot tell a legitimately empty result from a failed or
partial one, so aggregation records one outcome per fetch and per occasion
discovery. The outcomes decide whether the run may replace the public site.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal


if TYPE_CHECKING:
    from boringhannover.occasions import OccasionDefinition
    from boringhannover.output import EventsData

__all__ = [
    "IncompleteDiscoveryError",
    "SourceOutcome",
    "describe_error",
    "publication_refusal",
]

Operation = Literal["fetch", "discover_occasions"]
State = Literal["success", "empty", "partial", "failed"]
Completion = Literal["complete", "incomplete", "unknown"]

_MAX_REASON_LENGTH = 200


class IncompleteDiscoveryError(Exception):
    """Occasion discovery stopped short but kept every occasion it read."""

    def __init__(self, occasions: list[OccasionDefinition], reason: str) -> None:
        super().__init__(reason)
        self.occasions = occasions
        self.reason = reason


def describe_error(exc: BaseException) -> str:
    """Return an exception's type and first line, short enough for one log line."""
    lines = str(exc).strip().splitlines()
    text = f"{type(exc).__name__}: {lines[0]}" if lines else type(exc).__name__
    return text[:_MAX_REASON_LENGTH]


@dataclass(frozen=True, slots=True)
class SourceOutcome:
    """One source operation's result in one run.

    ``count`` is the number of usable items the operation produced, kept
    even when it stopped early. ``completion`` is only "complete" when the
    operation itself confirmed it read the whole source; a fetch adapter
    cannot, so its zero is never proof of an empty source.
    """

    source: str
    operation: Operation
    state: State
    count: int
    completion: Completion
    reason: str = ""

    @classmethod
    def finished(
        cls,
        source: str,
        operation: Operation,
        count: int,
        *,
        completion: Completion,
    ) -> SourceOutcome:
        """Record an operation that returned normally."""
        return cls(
            source, operation, "success" if count else "empty", count, completion
        )

    @classmethod
    def partial(
        cls,
        source: str,
        operation: Operation,
        count: int,
        reason: str,
    ) -> SourceOutcome:
        """Record an operation that kept ``count`` items but stopped short."""
        return cls(source, operation, "partial", count, "incomplete", reason)

    @classmethod
    def failed(
        cls,
        source: str,
        operation: Operation,
        exc: BaseException,
    ) -> SourceOutcome:
        """Record an operation that produced nothing usable."""
        return cls(source, operation, "failed", 0, "incomplete", describe_error(exc))

    def __str__(self) -> str:
        text = (
            f"{self.source} {self.operation}: {self.state}, "
            f"{self.count} usable, completion {self.completion}"
        )
        return f"{text} ({self.reason})" if self.reason else text


def publication_refusal(events_data: EventsData) -> str | None:
    """Return why this run must not replace the public site, or None if it may.

    Every publication replaces the whole public inventory, and nothing yet
    carries forward what a run failed to see (#26). So:

    - Occasion discovery is critical. An occasion missing from a failed or
      partial discovery would disappear from the site although nothing says
      it ended. Only a complete discovery may be published, including a
      complete empty one.
    - Fetches stay isolated: a failed venue costs only its own events. But a
      replacement without any movie or Radar event would empty the site on no
      evidence, since no fetch can confirm it read a complete source. What
      counts is what would be published: rows a source returned may all lie
      outside the window, so fetch counts serve only as diagnosis.
    """
    outcomes = events_data["source_outcomes"]
    unsafe = [
        outcome
        for outcome in outcomes
        if outcome.operation == "discover_occasions"
        and outcome.completion != "complete"
    ]
    if unsafe:
        return "incomplete occasion discovery: " + "; ".join(map(str, unsafe))

    if not events_data["movies_this_week"] and not events_data["big_events_radar"]:
        failed = [
            str(outcome)
            for outcome in outcomes
            if outcome.operation == "fetch" and outcome.state == "failed"
        ]
        return "no events to publish" + (": " + "; ".join(failed) if failed else "")
    return None
