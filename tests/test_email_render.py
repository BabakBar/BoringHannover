"""Rendering: one content model, an HTML and a plain-text body that agree."""

from __future__ import annotations

import re
from datetime import datetime

from boringhannover.constants import BERLIN_TZ
from boringhannover.newsletter.content import (
    EditionContent,
    EditionItem,
    EditionSection,
)
from boringhannover.newsletter.render import render_edition


UNSUBSCRIBE = "https://lists.example.org/u/%%TOKEN%%"


def _content(*sections: EditionSection) -> EditionContent:
    return EditionContent(
        key="hannover:2026-W35:en",
        city_id="hannover",
        locale="en",
        year=2026,
        week=35,
        window_start=datetime(2026, 8, 27, tzinfo=BERLIN_TZ).date(),
        window_end=datetime(2026, 9, 2, tzinfo=BERLIN_TZ).date(),
        generated_at=datetime(2026, 8, 27, 0, 12, tzinfo=BERLIN_TZ),
        sections=sections,
        revision="f" * 64,
    )


def _sample() -> EditionContent:
    return _content(
        EditionSection(
            key="movies",
            title="Original-version cinema",
            items=(
                EditionItem(
                    title="Die Odyssee",
                    date_display="Thu 27 Aug",
                    date_iso="2026-08-27",
                    time="20:15",
                    venue="Astor Grand Cinema",
                    url="https://hannover.premiumkino.de/film/die-odyssee",
                    note="EN · 2h52m · FSK12",
                ),
            ),
        ),
        EditionSection(
            key="radar",
            title="On the radar",
            items=(
                EditionItem(
                    title="Some Band",
                    date_display="Sat 29 Aug",
                    date_iso="2026-08-29",
                    time="20:00",
                    venue="Capitol Hannover",
                    url="https://www.capitol-hannover.de/events/some-band",
                    note="Live Music",
                ),
            ),
        ),
    )


def _render(content: EditionContent | None = None) -> object:
    return render_edition(content or _sample(), unsubscribe_url=UNSUBSCRIBE)


def test_subject_names_the_city_and_the_covered_week() -> None:
    assert _render().subject == "Hannover this week · 27 Aug - 2 Sep"  # type: ignore[attr-defined]


def test_html_lists_every_item_with_its_canonical_link() -> None:
    rendered = _render()

    assert "Die Odyssee" in rendered.html  # type: ignore[attr-defined]
    assert "Some Band" in rendered.html  # type: ignore[attr-defined]
    assert 'href="https://www.capitol-hannover.de/events/some-band"' in rendered.html  # type: ignore[attr-defined]


def test_plain_text_lists_every_item_and_carries_no_markup() -> None:
    rendered = _render()

    assert "Die Odyssee" in rendered.text  # type: ignore[attr-defined]
    assert "Capitol Hannover" in rendered.text  # type: ignore[attr-defined]
    assert "<" not in rendered.text  # type: ignore[attr-defined]


def test_section_titles_appear_in_both_bodies() -> None:
    rendered = _render()

    for title in ("Original-version cinema", "On the radar"):
        assert title in rendered.html  # type: ignore[attr-defined]
        # Plain-text section headers are uppercased as a deliberate convention.
        assert title.upper() in rendered.text  # type: ignore[attr-defined]


def test_titles_are_escaped_in_html_but_intact_in_text() -> None:
    content = _content(
        EditionSection(
            key="radar",
            title="On the radar",
            items=(
                EditionItem(
                    title="Rock & <Roll>",
                    date_display="Sat 29 Aug",
                    date_iso="2026-08-29",
                    time="20:00",
                    venue="Faust",
                    url="https://kulturzentrum-faust.de/rock",
                ),
            ),
        )
    )

    rendered = render_edition(content, unsubscribe_url=UNSUBSCRIBE)

    assert "Rock &amp; &lt;Roll&gt;" in rendered.html
    assert "<Roll>" not in rendered.html
    assert "Rock & <Roll>" in rendered.text


def test_urls_are_escaped_in_html_attributes() -> None:
    content = _content(
        EditionSection(
            key="radar",
            title="On the radar",
            items=(
                EditionItem(
                    title="Quoted",
                    date_display="Sat 29 Aug",
                    date_iso="2026-08-29",
                    time="20:00",
                    venue="Faust",
                    url='https://example.org/a"onmouseover="alert(1)',
                ),
            ),
        )
    )

    rendered = render_edition(content, unsubscribe_url=UNSUBSCRIBE)

    assert 'onmouseover="alert(1)"' not in rendered.html
    assert "&quot;" in rendered.html


def test_both_bodies_carry_a_visible_unsubscribe_link() -> None:
    rendered = _render()

    assert UNSUBSCRIBE in rendered.html  # type: ignore[attr-defined]
    assert UNSUBSCRIBE in rendered.text  # type: ignore[attr-defined]
    assert "Unsubscribe" in rendered.html  # type: ignore[attr-defined]


def test_one_click_unsubscribe_headers_are_present() -> None:
    rendered = _render()

    assert rendered.headers["List-Unsubscribe"] == f"<{UNSUBSCRIBE}>"  # type: ignore[attr-defined]
    assert rendered.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"  # type: ignore[attr-defined]


def test_the_edition_key_travels_with_the_message() -> None:
    rendered = _render()

    assert rendered.headers["X-Edition-Key"] == "hannover:2026-W35:en"  # type: ignore[attr-defined]
    assert rendered.headers["X-Edition-Revision"] == "f" * 64  # type: ignore[attr-defined]


def test_no_images_are_embedded_so_there_is_no_open_tracking() -> None:
    assert "<img" not in _render().html.lower()  # type: ignore[attr-defined]


def test_links_are_not_redirect_wrapped() -> None:
    hrefs = re.findall(r'href="([^"]+)"', _render().html)  # type: ignore[attr-defined]

    assert all(href.startswith(("https://", "mailto:")) for href in hrefs), (
        "every link must be a plain canonical URL"
    )
    assert not any("utm_" in href or "/track/" in href for href in hrefs)


def test_html_declares_its_language_for_screen_readers() -> None:
    assert 'lang="en"' in _render().html  # type: ignore[attr-defined]


def test_rendering_is_deterministic() -> None:
    first = _render()
    second = _render()

    assert first.html == second.html  # type: ignore[attr-defined]
    assert first.text == second.text  # type: ignore[attr-defined]
