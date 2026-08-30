"""Email delivery boundary: a rendered edition becomes a sent campaign.

The newsletter package works at edition/campaign level only and never stores
subscriber data. A provider receives a fully rendered edition and returns an
idempotency-safe result keyed by a provider message id.

``PreviewProvider`` is the only built-in provider: it writes the rendered bodies
to disk so an operator can approve them before a hosted provider is configured.
A hosted provider (Resend, Buttondown, Mailjet, ...) implements ``EmailProvider``
and is selected via ``NEWSLETTER_PROVIDER`` once its data-processing agreement,
sending identity (SPF/DKIM/DMARC) and suppression handling are in place.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from boringhannover.newsletter.render import RenderedEdition


__all__ = [
    "EmailProvider",
    "PreviewProvider",
    "ProviderError",
    "SendOutcome",
    "resolve_provider",
]


@dataclass(frozen=True, slots=True)
class SendOutcome:
    """What the provider reported for one delivery attempt."""

    provider_message_id: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True when the provider accepted the send without reporting an error."""
        return self.error is None


class ProviderError(RuntimeError):
    """A provider could not deliver; the attempt must be marked failed."""


class EmailProvider(Protocol):
    """Turns a rendered edition into a delivered campaign."""

    name: str

    def send(self, edition: RenderedEdition) -> SendOutcome:
        """Deliver one edition and report a provider-side idempotency key."""


class PreviewProvider:
    """Writes the rendered edition to disk instead of delivering it."""

    name = "preview"

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def send(self, edition: RenderedEdition) -> SendOutcome:
        """Write the four render outputs so a human can approve the edition."""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            (self.output_dir / "subject.txt").write_text(
                f"{edition.subject}\n", encoding="utf-8"
            )
            (self.output_dir / "body.html").write_text(edition.html, encoding="utf-8")
            (self.output_dir / "body.txt").write_text(edition.text, encoding="utf-8")
            (self.output_dir / "headers.json").write_text(
                json.dumps(edition.headers, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            return SendOutcome(error=f"cannot write preview: {exc}")
        return SendOutcome(
            provider_message_id=f"preview:{edition.headers['X-Edition-Key']}"
        )


def resolve_provider(name: str, preview_dir: str | Path) -> EmailProvider:
    """Return the provider for ``name``.

    Only ``preview`` is built in. A real provider is added here once one is
    selected; an unknown name fails closed rather than silently not sending.
    """
    if name == "preview":
        return PreviewProvider(preview_dir)
    raise ProviderError(
        f"unknown newsletter provider {name!r}; only 'preview' is built in"
    )
