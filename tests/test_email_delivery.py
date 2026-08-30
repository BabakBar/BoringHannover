"""Delivery is the only path that writes the ledger and calls the provider."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from boringhannover.constants import BERLIN_TZ
from boringhannover.newsletter.config import NewsletterConfig
from boringhannover.newsletter.delivery import deliver_edition, preview_edition
from boringhannover.newsletter.ledger import SendLedger
from boringhannover.newsletter.provider import SendOutcome
from boringhannover.newsletter.render import RenderedEdition


GENERATED_AT = datetime(2026, 8, 27, 0, 12, tzinfo=BERLIN_TZ)
NOW = datetime(2026, 8, 27, 9, 0, tzinfo=BERLIN_TZ)


class _FakeProvider:
    """A provider that returns a fixed outcome and records every call."""

    name = "fake"

    def __init__(
        self,
        *,
        message_id: str | None = "campaign-1",
        error: str | None = None,
    ) -> None:
        self.message_id = message_id
        self.error = error
        self.calls: list[RenderedEdition] = []

    def send(self, edition: RenderedEdition) -> SendOutcome:
        self.calls.append(edition)
        return SendOutcome(provider_message_id=self.message_id, error=self.error)


def _artifact(*, with_events: bool = True) -> dict[str, Any]:
    concerts = (
        [
            {
                "title": "Some Band",
                "dateISO": "2026-08-29",
                "time": "20:00",
                "venue": "Capitol Hannover",
                "url": "https://www.capitol-hannover.de/events/some-band",
            }
        ]
        if with_events
        else []
    )
    return {
        "meta": {
            "week": 35,
            "year": 2026,
            "updatedAt": "Thu 27 Aug 00:12",
            "updatedAtISO": GENERATED_AT.isoformat(),
        },
        "movies": [],
        "concerts": concerts,
        "occasions": [],
    }


def _config(tmp_path: Path, *, healthy: bool = True) -> NewsletterConfig:
    artifact = tmp_path / "web_events.json"
    artifact.write_text(json.dumps(_artifact()), encoding="utf-8")
    if healthy:
        (tmp_path / "run_health.json").write_text(
            json.dumps(
                {"status": "ok", "sources": [{"name": "Capitol", "status": "ok"}]}
            ),
            encoding="utf-8",
        )
    return NewsletterConfig(
        artifact_path=artifact,
        ledger_path=tmp_path / "send_log.json",
        health_path=tmp_path / "run_health.json",
        preview_dir=tmp_path / "preview",
        city_id="hannover",
        locale="en",
        audience="hannover-weekly-en",
        unsubscribe_url="https://example.org/u/token",
        provider="fake",
    )


def test_deliver_sends_and_records_completion(tmp_path: Path) -> None:
    provider = _FakeProvider()

    result = deliver_edition(_config(tmp_path), provider=provider, now=NOW)

    assert result.sent
    assert result.provider_message_id == "campaign-1"
    assert len(provider.calls) == 1
    assert SendLedger(tmp_path / "send_log.json").is_completed("hannover:2026-W35:en")


def test_deliver_holds_without_touching_the_provider(tmp_path: Path) -> None:
    provider = _FakeProvider()
    config = _config(tmp_path)
    config.artifact_path.unlink()

    result = deliver_edition(config, provider=provider, now=NOW)

    assert not result.sent
    assert result.decision.hold_codes == ("artifact_missing",)
    assert provider.calls == []


def test_deliver_refuses_when_approval_is_still_required(tmp_path: Path) -> None:
    provider = _FakeProvider()

    result = deliver_edition(
        _config(tmp_path, healthy=False), provider=provider, now=NOW
    )

    assert not result.sent
    assert result.error == "requires_approval"
    assert provider.calls == []


def test_deliver_respects_an_explicit_approval(tmp_path: Path) -> None:
    provider = _FakeProvider()

    result = deliver_edition(
        _config(tmp_path, healthy=False),
        provider=provider,
        now=NOW,
        approved=True,
    )

    assert result.sent


def test_deliver_marks_the_attempt_failed_on_provider_error(tmp_path: Path) -> None:
    config = _config(tmp_path)

    result = deliver_edition(config, provider=_FakeProvider(error="timeout"), now=NOW)

    assert not result.sent
    assert result.error == "timeout"
    record = SendLedger(config.ledger_path).record_for("hannover:2026-W35:en")
    assert record is not None
    assert record.status == "failed"


def test_deliver_marks_the_attempt_failed_without_a_message_id(tmp_path: Path) -> None:
    config = _config(tmp_path)

    result = deliver_edition(config, provider=_FakeProvider(message_id=None), now=NOW)

    assert not result.sent
    assert "no message id" in (result.error or "")
    record = SendLedger(config.ledger_path).record_for("hannover:2026-W35:en")
    assert record is not None
    assert record.status == "failed"


def test_a_second_delivery_is_held_by_the_ledger(tmp_path: Path) -> None:
    config = _config(tmp_path)
    provider = _FakeProvider()

    first = deliver_edition(config, provider=provider, now=NOW)
    assert first.sent

    second = deliver_edition(config, provider=_FakeProvider(), now=NOW)

    assert not second.sent
    assert second.decision.hold_codes == ("already_sent",)


def test_preview_writes_files_and_never_touches_the_ledger(tmp_path: Path) -> None:
    config = _config(tmp_path)

    preview = preview_edition(config, now=NOW)

    assert preview.rendered is not None
    assert (tmp_path / "preview" / "body.html").exists()
    assert (tmp_path / "preview" / "body.txt").exists()
    assert not (tmp_path / "send_log.json").exists()


def test_preview_of_a_missing_artifact_has_nothing_to_render(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.artifact_path.unlink()

    preview = preview_edition(config, now=NOW)

    assert preview.rendered is None
    assert preview.decision.hold_codes == ("artifact_missing",)
