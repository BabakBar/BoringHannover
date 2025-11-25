"""Text sanitization for untrusted scraped content.

This module provides security functions to sanitize data from external sources
before it flows to the frontend. Uses nh3 (Rust-based Ammonia bindings) for
HTML sanitization - NOT bleach (deprecated January 2023).

Usage:
    from kinoweek.sanitize import sanitize_text, sanitize_url

    title = sanitize_text(scraped_title)
    url = sanitize_url(scraped_url)
"""

from __future__ import annotations

import html
import re
from typing import Final

import nh3


__all__ = [
    "MAX_DESCRIPTION_LENGTH",
    "MAX_TITLE_LENGTH",
    "MAX_URL_LENGTH",
    "MAX_VENUE_LENGTH",
    "sanitize_text",
    "sanitize_url",
]

# Maximum lengths to prevent data corruption attacks
MAX_TITLE_LENGTH: Final[int] = 200
MAX_VENUE_LENGTH: Final[int] = 100
MAX_URL_LENGTH: Final[int] = 500
MAX_DESCRIPTION_LENGTH: Final[int] = 1000


def sanitize_text(text: str | None, max_length: int = 500) -> str:
    """Remove all HTML tags and limit length.

    Uses nh3 (Rust-based) for fast, safe HTML stripping.
    All HTML tags are removed - no allowlist.

    Args:
        text: Raw text that may contain HTML.
        max_length: Maximum allowed length (default 500).

    Returns:
        Sanitized plain text, or empty string if input is None/empty.

    Example:
        >>> sanitize_text("<script>alert('xss')</script>Hello")
        'Hello'
        >>> sanitize_text("A" * 1000, max_length=100)
        'AAA...AAA...'
    """
    if not text:
        return ""

    # nh3.clean with empty tags set strips ALL HTML
    # This is safer than trying to maintain an allowlist
    cleaned = nh3.clean(text, tags=set())

    # Decode HTML entities (e.g., &amp; -> &)
    cleaned = html.unescape(cleaned)

    # Normalize whitespace (collapse multiple spaces/newlines)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Enforce length limit with ellipsis
    if len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 3] + "..."

    return cleaned


def sanitize_url(url: str | None) -> str:
    """Validate and sanitize URL to prevent injection attacks.

    Only allows http:// and https:// schemes. Blocks javascript:,
    data:, vbscript:, and other dangerous protocols.

    Args:
        url: URL string to validate.

    Returns:
        Validated URL, or empty string if invalid/dangerous.

    Example:
        >>> sanitize_url("https://example.com/event")
        'https://example.com/event'
        >>> sanitize_url("javascript:alert('xss')")
        ''
        >>> sanitize_url("data:text/html,<script>...")
        ''
    """
    if not url:
        return ""

    url = url.strip()

    # Reject URLs that are too long (potential DoS)
    if len(url) > MAX_URL_LENGTH:
        return ""

    # Normalize for comparison (case-insensitive protocol check)
    url_lower = url.lower()

    # Block dangerous protocols
    dangerous_protocols = (
        "javascript:",
        "data:",
        "vbscript:",
        "file:",
        "about:",
        "blob:",
    )
    if any(url_lower.startswith(proto) for proto in dangerous_protocols):
        return ""

    # Only allow http/https
    if not url_lower.startswith(("http://", "https://")):
        return ""

    return url
