"""Render one edition as HTML and plain text.

Both bodies come from the same content model, so they cannot drift. The HTML is
deliberately image-free: no images means no tracking pixel, which is what the
privacy notice will promise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import TYPE_CHECKING, Final

from boringhannover.event_time import UNKNOWN_TIME_LABEL


if TYPE_CHECKING:
    from boringhannover.newsletter.content import (
        EditionContent,
        EditionItem,
        EditionSection,
    )

__all__ = ["SITE_URL", "RenderedEdition", "render_edition"]

SITE_URL: Final[str] = "https://boringhannover.de"
CITY_LABEL: Final[str] = "Hannover"

_INK: Final[str] = "#1a1a1a"
_MUTED: Final[str] = "#5f5f5f"
_DATA: Final[str] = "#7a6238"
_ACCENT: Final[str] = "#b91c1c"
_PAPER: Final[str] = "#fafaf9"
_RULE: Final[str] = "#e0dfdd"
_FONT: Final[str] = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
)


@dataclass(frozen=True, slots=True)
class RenderedEdition:
    """A ready-to-send edition in both required body formats."""

    subject: str
    html: str
    text: str
    headers: dict[str, str] = field(default_factory=dict)


def _format_range(content: EditionContent) -> str:
    """Format the covered window as '27 Aug - 2 Sep'."""
    start, end = content.window_start, content.window_end
    return f"{start.day} {start:%b} - {end.day} {end:%b}"


def _item_meta(item: EditionItem) -> str:
    """One line of context: time, venue and any source-provided note."""
    parts = [item.time or UNKNOWN_TIME_LABEL, item.venue, item.note]
    return " · ".join(part for part in parts if part)


def _html_item(item: EditionItem) -> str:
    """Render one item as a table row."""
    title = escape(item.title)
    linked = (
        f'<a href="{escape(item.url, quote=True)}" '
        f'style="color:{_INK};text-decoration:underline;">{title}</a>'
        if item.url
        else title
    )
    return (
        '<tr><td style="padding:10px 0;border-bottom:1px solid '
        f'{_RULE};font-family:{_FONT};">'
        f'<div style="font-size:12px;letter-spacing:0.08em;text-transform:uppercase;'
        f'color:{_DATA};">{escape(item.date_display)}</div>'
        f'<div style="font-size:16px;line-height:1.35;color:{_INK};padding-top:2px;">'
        f"{linked}</div>"
        f'<div style="font-size:13px;color:{_MUTED};padding-top:2px;">'
        f"{escape(_item_meta(item))}</div>"
        "</td></tr>"
    )


def _html_section(section: EditionSection) -> str:
    """Render one titled section."""
    rows = "".join(_html_item(item) for item in section.items)
    return (
        f'<h2 style="font-family:{_FONT};font-size:13px;letter-spacing:0.14em;'
        f"text-transform:uppercase;color:{_ACCENT};margin:32px 0 4px;"
        f'font-weight:600;">{escape(section.title)}</h2>'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'width="100%" style="width:100%;border-collapse:collapse;">{rows}</table>'
    )


def _render_html(content: EditionContent, *, unsubscribe_url: str) -> str:
    """Render the HTML body."""
    sections = "".join(_html_section(section) for section in content.sections)
    unsubscribe = escape(unsubscribe_url, quote=True)
    week_range = escape(_format_range(content))

    return (
        f'<!doctype html><html lang="{escape(content.locale, quote=True)}">'
        '<head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light">'
        f"<title>{CITY_LABEL} this week · {week_range}</title></head>"
        f'<body style="margin:0;padding:0;background:{_PAPER};">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'width="100%" style="width:100%;background:{_PAPER};">'
        '<tr><td align="center" style="padding:24px 16px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'width="600" style="width:100%;max-width:600px;text-align:left;">'
        "<tr><td>"
        f'<p style="font-family:{_FONT};font-size:12px;letter-spacing:0.14em;'
        f'text-transform:uppercase;color:{_MUTED};margin:0;">'
        f"Week {content.week} · {week_range}</p>"
        f'<h1 style="font-family:{_FONT};font-size:26px;line-height:1.2;'
        f'color:{_INK};margin:6px 0 0;">{CITY_LABEL} this week</h1>'
        f'<p style="font-family:{_FONT};font-size:14px;line-height:1.5;'
        f'color:{_MUTED};margin:10px 0 0;">'
        f"{content.item_count} things worth leaving the flat for, "
        "picked from the same data as "
        f'<a href="{SITE_URL}" style="color:{_INK};">boringhannover.de</a>.</p>'
        f"{sections}"
        f'<p style="font-family:{_FONT};font-size:13px;line-height:1.6;'
        f"color:{_MUTED};margin:36px 0 0;border-top:1px solid {_RULE};"
        'padding-top:16px;">'
        f"You get this because you confirmed a subscription to the {CITY_LABEL} "
        "weekly digest. Nothing in this email is tracked: no open pixel, no "
        "click redirects.<br>"
        f'<a href="{unsubscribe}" style="color:{_ACCENT};">Unsubscribe</a> · '
        f'<a href="{SITE_URL}" style="color:{_MUTED};">boringhannover.de</a>'
        "</p>"
        "</td></tr></table></td></tr></table></body></html>"
    )


def _render_text(content: EditionContent, *, unsubscribe_url: str) -> str:
    """Render the plain-text body."""
    week_range = _format_range(content)
    lines: list[str] = [
        f"{CITY_LABEL.upper()} THIS WEEK",
        f"Week {content.week} · {week_range}",
        "",
        f"{content.item_count} things worth leaving the flat for, picked from the",
        f"same data as {SITE_URL}",
    ]

    for section in content.sections:
        lines.extend(["", section.title.upper(), "-" * len(section.title)])
        for item in section.items:
            lines.append(f"{item.date_display} — {item.title}")
            lines.append(f"  {_item_meta(item)}")
            if item.url:
                lines.append(f"  {item.url}")
            lines.append("")

    lines.extend(
        [
            "",
            "--",
            f"You get this because you confirmed a subscription to the {CITY_LABEL}",
            "weekly digest. Nothing in this email is tracked: no open pixel, no",
            "click redirects.",
            f"Unsubscribe: {unsubscribe_url}",
            SITE_URL,
        ]
    )
    return "\n".join(lines)


def render_edition(
    content: EditionContent,
    *,
    unsubscribe_url: str,
) -> RenderedEdition:
    """Render one edition into subject, HTML body, text body and headers.

    Args:
        content: The edition content model.
        unsubscribe_url: Provider unsubscribe link or merge tag. It is placed in
            both bodies and in the one-click unsubscribe headers.

    Returns:
        The rendered edition.
    """
    return RenderedEdition(
        subject=f"{CITY_LABEL} this week · {_format_range(content)}",
        html=_render_html(content, unsubscribe_url=unsubscribe_url),
        text=_render_text(content, unsubscribe_url=unsubscribe_url),
        headers={
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            "X-Edition-Key": content.key,
            "X-Edition-Revision": content.revision,
        },
    )
