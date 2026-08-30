"""Weekly email digest: edition identity, send gate, rendering, and delivery.

Deliberately holds no subscriber data. Recipient addresses live with the email
service provider; this package works at edition/campaign level only. The content
is derived from the same canonical ``web_events.json`` the website is built
from, and delivery is the only path that records a send in the ledger.
"""

from __future__ import annotations

from boringhannover.newsletter.config import NewsletterConfig
from boringhannover.newsletter.content import EditionContent, build_edition_content
from boringhannover.newsletter.delivery import (
    DeliveryResult,
    deliver_edition,
    preview_edition,
)
from boringhannover.newsletter.edition import build_edition_key
from boringhannover.newsletter.gate import GateDecision, evaluate_send_gate
from boringhannover.newsletter.ledger import SendLedger
from boringhannover.newsletter.provider import (
    EmailProvider,
    PreviewProvider,
    ProviderError,
    SendOutcome,
    resolve_provider,
)
from boringhannover.newsletter.render import RenderedEdition, render_edition


__all__ = [
    "DeliveryResult",
    "EditionContent",
    "EmailProvider",
    "GateDecision",
    "NewsletterConfig",
    "PreviewProvider",
    "ProviderError",
    "RenderedEdition",
    "SendLedger",
    "SendOutcome",
    "build_edition_content",
    "build_edition_key",
    "deliver_edition",
    "evaluate_send_gate",
    "preview_edition",
    "render_edition",
    "resolve_provider",
]
