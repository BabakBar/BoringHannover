"""One availability policy for every published listing (#134).

Adapters report what a venue states, and many state nothing. The exporter
used to fill that gap with "available", so a venue that announced a
cancellation only in the title (ZAG Arena: "KONSTANTINOS ARGIROS - ABGESAGT")
published as an available concert.

The rules, in order:

1. An explicit cancellation, postponement or rescheduling from the adapter
   stands.
2. A cancellation or postponement announced in the title wins over any other
   explicit status: the venue's own wording is the stronger evidence.
3. An explicit ``sold_out`` or ``available`` stands.
4. Anything else is ``unknown``. Absent ticket information is never treated
   as proof of availability.

Cancelled and postponed rows stay published and are labelled as such, rather
than dropped: carry-forward matches fresh rows against the Radar to move a
cancellation into a known occasion's programme, and the source wording is
kept in the title.
"""

from __future__ import annotations

import re
from typing import Final


__all__ = ["CANCELLED", "POSTPONED", "listing_status"]

CANCELLED: Final = "cancelled"
POSTPONED: Final = "postponed"
_UNKNOWN: Final = "unknown"

# Statuses that already say the listed date will not happen as announced.
_EXPLICIT_CHANGE: Final = frozenset(
    {"cancelled", "canceled", "postponed", "rescheduled"}
)
_EXPLICIT_OTHER: Final = frozenset({"sold_out", "available"})

# Whole words only: "abgesagt" must not match inside another word.
_TITLE_CANCELLED: Final = re.compile(
    r"\b(?:abgesagt|entf(?:ä|ae)llt|f(?:ä|ae)llt\s+aus|ersatzlos\s+gestrichen|"
    r"cancell?ed)\b",
    re.IGNORECASE,
)
_TITLE_POSTPONED: Final = re.compile(r"\b(?:verschoben|postponed)\b", re.IGNORECASE)


def listing_status(title: str, status: object) -> str:
    """Return the status to publish for a listing with this title and status."""
    explicit = str(status).strip().casefold() if status else ""
    if explicit in _EXPLICIT_CHANGE:
        return explicit
    if _TITLE_CANCELLED.search(title):
        return CANCELLED
    if _TITLE_POSTPONED.search(title):
        return POSTPONED
    if explicit in _EXPLICIT_OTHER:
        return explicit
    return _UNKNOWN
