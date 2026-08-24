"""Shared fail-closed helpers for German month parsing."""

from __future__ import annotations

import logging
from typing import Final

from boringhannover.config import GERMAN_MONTH_MAP


logger = logging.getLogger(__name__)

__all__ = [
    "UNKNOWN_MONTH_TOKEN",
    "log_unknown_month",
    "lookup_german_month",
]

UNKNOWN_MONTH_TOKEN: Final[str] = "unknown_month_token"
"""Reason code for a month token that has no supported mapping."""


def lookup_german_month(month_str: str) -> int | None:
    """Resolve a German month token without guessing or logging.

    Callers own the source context and must log a rejection with
    :func:`log_unknown_month` before dropping the occurrence.
    """
    return GERMAN_MONTH_MAP.get(month_str.strip().lower())


def log_unknown_month(
    month_str: str,
    *,
    source_key: str,
    raw_value: str,
    field: str = "start",
) -> None:
    """Log an unknown month with the complete source date value.

    Args:
        month_str: Month token extracted from ``raw_value``.
        source_key: Registered source identifier.
        raw_value: Short raw date field, not an HTML document or page body.
        field: Logical date field being parsed.
    """
    normalized_token = month_str.strip().lower()
    failure = {
        "code": UNKNOWN_MONTH_TOKEN,
        "sourceKey": source_key,
        "field": field,
        "rawValue": raw_value,
        "normalizedToken": normalized_token,
    }
    logger.warning(
        "Rejected unparseable date component: %s",
        failure,
        extra={"date_parse_failure": failure},
    )
