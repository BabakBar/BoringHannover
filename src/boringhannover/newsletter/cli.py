"""Command-line interface for the weekly email digest.

Two commands, both idempotency-safe:

    boringhannover-newsletter preview   # render + gate + write preview files
    boringhannover-newsletter send      # gate + deliver via the provider

``send`` fails closed: a held edition, a still-required approval (without
``--approve``), or an unconfigured provider all exit non-zero without sending.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import NoReturn

from boringhannover.constants import BERLIN_TZ
from boringhannover.newsletter.config import NewsletterConfig
from boringhannover.newsletter.delivery import deliver_edition, preview_edition
from boringhannover.newsletter.gate import GateDecision
from boringhannover.newsletter.provider import ProviderError, resolve_provider


__all__ = ["main"]

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="boringhannover-newsletter",
        description="Build, preview and deliver the weekly email digest.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    preview = subparsers.add_parser(
        "preview",
        help="Render the edition and write it to the preview directory.",
    )
    preview.add_argument(
        "--output",
        help="Preview directory (overrides NEWSLETTER_PREVIEW_DIR).",
    )

    send = subparsers.add_parser(
        "send",
        help="Deliver the edition through the configured provider.",
    )
    send.add_argument(
        "--approve",
        action="store_true",
        help="Explicitly approve this send (overrides the approval requirement).",
    )
    send.add_argument(
        "--provider",
        help="Provider to use (overrides NEWSLETTER_PROVIDER).",
    )
    return parser


def _report_holds(decision: GateDecision) -> None:
    for hold in decision.holds:
        logger.error("held: %s - %s", hold.code, hold.detail)
    if decision.requires_approval:
        logger.warning(
            "this edition still requires manual approval (no run-health report); "
            "run `send --approve` only after reviewing the preview"
        )


def _run_preview(config: NewsletterConfig) -> int:
    preview = preview_edition(config, now=datetime.now(BERLIN_TZ))
    _report_holds(preview.decision)

    if preview.rendered is None:
        logger.error("no edition could be built; nothing to preview")
        return 1

    logger.info("Preview written to %s", config.preview_dir)
    logger.info("Edition key: %s", preview.rendered.headers["X-Edition-Key"])
    logger.info("Subject: %s", preview.rendered.subject)
    return 0


def _run_send(config: NewsletterConfig, *, provider: str, approved: bool) -> int:
    if provider == "preview":
        logger.error(
            "`preview` writes files but does not send; configure "
            "NEWSLETTER_PROVIDER with a real provider before `send`"
        )
        return 1

    try:
        resolved = resolve_provider(provider, config.preview_dir)
    except ProviderError as exc:
        logger.error("%s", exc)
        return 1

    result = deliver_edition(
        config,
        provider=resolved,
        now=datetime.now(BERLIN_TZ),
        approved=approved,
    )
    _report_holds(result.decision)

    if result.sent:
        content = result.decision.content
        assert content is not None
        logger.info(
            "Sent edition %s (%s)",
            content.key,
            result.provider_message_id,
        )
        return 0

    logger.error("edition not sent: %s", result.error or "held by the send gate")
    return 1


def main(argv: Sequence[str] | None = None) -> NoReturn:
    """Run the newsletter CLI and exit with the appropriate status code."""
    _configure_logging()
    args = _build_parser().parse_args(argv)
    config = NewsletterConfig.from_env()

    if args.command == "preview":
        if getattr(args, "output", None):
            config = replace(config, preview_dir=Path(args.output))
        sys.exit(_run_preview(config))

    if args.command == "send":
        provider = getattr(args, "provider", None) or config.provider
        sys.exit(_run_send(config, provider=provider, approved=bool(args.approve)))

    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover
