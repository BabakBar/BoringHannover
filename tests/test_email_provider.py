"""The provider boundary: preview writes files, unknown names fail closed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boringhannover.newsletter.provider import (
    PreviewProvider,
    ProviderError,
    resolve_provider,
)
from boringhannover.newsletter.render import RenderedEdition


def _rendered() -> RenderedEdition:
    return RenderedEdition(
        subject="Hannover this week",
        html="<p>hello</p>",
        text="hello",
        headers={"X-Edition-Key": "hannover:2026-W35:en"},
    )


def test_preview_writes_subject_html_text_and_headers(tmp_path: Path) -> None:
    rendered = _rendered()

    outcome = PreviewProvider(tmp_path).send(rendered)

    assert outcome.ok
    assert outcome.provider_message_id == "preview:hannover:2026-W35:en"
    assert (tmp_path / "subject.txt").read_text(encoding="utf-8") == (
        rendered.subject + "\n"
    )
    assert (tmp_path / "body.html").read_text(encoding="utf-8") == rendered.html
    assert (tmp_path / "body.txt").read_text(encoding="utf-8") == rendered.text
    assert (
        json.loads((tmp_path / "headers.json").read_text(encoding="utf-8"))
        == rendered.headers
    )


def test_preview_reports_a_write_failure_instead_of_raising(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.write_text("not a directory", encoding="utf-8")

    outcome = PreviewProvider(occupied / "sub").send(_rendered())

    assert not outcome.ok
    assert outcome.error is not None
    assert "cannot write preview" in outcome.error


def test_resolve_preview_returns_the_preview_provider(tmp_path: Path) -> None:
    provider = resolve_provider("preview", tmp_path)

    assert isinstance(provider, PreviewProvider)


def test_resolve_unknown_provider_fails_closed() -> None:
    with pytest.raises(ProviderError, match="unknown newsletter provider"):
        resolve_provider("resend", ".")
