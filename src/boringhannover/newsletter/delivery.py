"""End-to-end newsletter workflows: preview and delivery.

Both paths build the edition from the canonical ``web_events.json`` artifact,
run the send gate, and render once. Preview is read-only: it writes the rendered
bodies to disk and never touches the ledger. Delivery is the only place the
ledger is written and a provider is called, so a retry can never double-send.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from boringhannover.constants import BERLIN_TZ
from boringhannover.newsletter.config import NewsletterConfig
from boringhannover.newsletter.gate import GateDecision, evaluate_send_gate
from boringhannover.newsletter.ledger import SendLedger
from boringhannover.newsletter.provider import EmailProvider, PreviewProvider
from boringhannover.newsletter.render import RenderedEdition, render_edition


if TYPE_CHECKING:
    from boringhannover.newsletter.content import EditionContent

__all__ = ["DeliveryResult", "EditionPreview", "deliver_edition", "preview_edition"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EditionPreview:
    """The gate verdict plus the rendered bodies, when content could be built."""

    decision: GateDecision
    rendered: RenderedEdition | None


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """What happened during one delivery attempt."""

    decision: GateDecision
    sent: bool
    provider_message_id: str | None = None
    error: str | None = None


def _evaluate(config: NewsletterConfig, now: datetime) -> GateDecision:
    return evaluate_send_gate(
        artifact_path=config.artifact_path,
        ledger=SendLedger(config.ledger_path),
        now=now,
        health_path=config.health_path,
        city_id=config.city_id,
        locale=config.locale,
    )


def _render(content: EditionContent, config: NewsletterConfig) -> RenderedEdition:
    return render_edition(content, unsubscribe_url=config.unsubscribe_url)


def preview_edition(
    config: NewsletterConfig, *, now: datetime | None = None
) -> EditionPreview:
    """Build, gate and render one edition, writing the bodies to the preview dir.

    The preview is written whenever the artifact yields content, even for a held
    edition, so an operator can see exactly what would (not) go out.
    """
    decision = _evaluate(config, now or datetime.now(BERLIN_TZ))

    rendered: RenderedEdition | None = None
    if decision.content is not None:
        rendered = _render(decision.content, config)
        outcome = PreviewProvider(config.preview_dir).send(rendered)
        if outcome.error is not None:
            logger.warning("Preview not written: %s", outcome.error)

    return EditionPreview(decision=decision, rendered=rendered)


def deliver_edition(
    config: NewsletterConfig,
    *,
    provider: EmailProvider,
    now: datetime | None = None,
    approved: bool = False,
) -> DeliveryResult:
    """Deliver one edition if the gate allows it.

    Args:
        config: Operational settings.
        provider: The provider that actually delivers the rendered edition.
        now: Current time, for staleness and ledger timestamps.
        approved: True when a human has explicitly approved this send. Without
            it, an edition whose gate still requires approval (no run-health
            report yet) is refused.

    Returns:
        The delivery result; ``sent`` is True only after the provider accepted
        the send and the ledger recorded it as completed.
    """
    current = now or datetime.now(BERLIN_TZ)
    decision = _evaluate(config, current)

    if not decision.allowed:
        return DeliveryResult(decision=decision, sent=False)

    if decision.requires_approval and not approved:
        return DeliveryResult(
            decision=decision,
            sent=False,
            error="requires_approval",
        )

    content = decision.content
    if content is None:
        return DeliveryResult(decision=decision, sent=False, error="no_content")

    rendered = _render(content, config)
    ledger = SendLedger(config.ledger_path)
    ledger.start(
        content.key,
        revision=content.revision,
        audience=config.audience,
        now=current,
    )

    outcome = provider.send(rendered)

    if outcome.error is not None:
        ledger.fail(content.key, reason=outcome.error, now=current)
        return DeliveryResult(decision=decision, sent=False, error=outcome.error)

    if outcome.provider_message_id is None:
        reason = "provider accepted the send but returned no message id"
        ledger.fail(content.key, reason=reason, now=current)
        return DeliveryResult(decision=decision, sent=False, error=reason)

    ledger.complete(
        content.key,
        provider_message_id=outcome.provider_message_id,
        now=current,
    )
    logger.info("Delivered edition %s (%s)", content.key, outcome.provider_message_id)
    return DeliveryResult(
        decision=decision,
        sent=True,
        provider_message_id=outcome.provider_message_id,
    )
