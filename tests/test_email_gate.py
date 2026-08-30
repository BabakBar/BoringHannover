"""The send gate decides whether an edition may leave the building."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from boringhannover.constants import BERLIN_TZ
from boringhannover.newsletter.gate import evaluate_send_gate
from boringhannover.newsletter.ledger import SendLedger


GENERATED_AT = datetime(2026, 8, 27, 0, 12, tzinfo=BERLIN_TZ)
NOW = datetime(2026, 8, 27, 9, 0, tzinfo=BERLIN_TZ)


def _artifact_payload(*, with_events: bool = True) -> dict[str, Any]:
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


def _write_artifact(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "web_events.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _evaluate(tmp_path: Path, **overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "artifact_path": tmp_path / "web_events.json",
        "ledger": SendLedger(tmp_path / "send_log.json"),
        "now": NOW,
        "health_path": tmp_path / "run_health.json",
    }
    kwargs.update(overrides)
    return evaluate_send_gate(**kwargs)


def test_a_fresh_artifact_with_events_is_allowed_but_needs_approval(
    tmp_path: Path,
) -> None:
    _write_artifact(tmp_path, _artifact_payload())

    decision = _evaluate(tmp_path)

    assert decision.allowed
    assert decision.hold_codes == ()
    assert decision.requires_approval, "no health report yet, so #27 demands a human"
    assert decision.content is not None
    assert decision.content.key == "hannover:2026-W35:en"


def test_a_missing_artifact_holds_the_edition(tmp_path: Path) -> None:
    decision = _evaluate(tmp_path)

    assert not decision.allowed
    assert decision.hold_codes == ("artifact_missing",)
    assert decision.content is None


def test_an_unreadable_artifact_holds_the_edition(tmp_path: Path) -> None:
    (tmp_path / "web_events.json").write_text("{ nope", encoding="utf-8")

    decision = _evaluate(tmp_path)

    assert not decision.allowed
    assert decision.hold_codes == ("artifact_unreadable",)


def test_a_stale_artifact_holds_the_edition(tmp_path: Path) -> None:
    _write_artifact(tmp_path, _artifact_payload())

    decision = _evaluate(tmp_path, now=GENERATED_AT + timedelta(hours=73))

    assert not decision.allowed
    assert decision.hold_codes == ("artifact_stale",)


def test_an_artifact_exactly_at_the_age_limit_still_passes(tmp_path: Path) -> None:
    _write_artifact(tmp_path, _artifact_payload())

    decision = _evaluate(tmp_path, now=GENERATED_AT + timedelta(hours=72))

    assert decision.allowed


def test_an_edition_with_nothing_to_say_holds(tmp_path: Path) -> None:
    _write_artifact(tmp_path, _artifact_payload(with_events=False))

    decision = _evaluate(tmp_path)

    assert not decision.allowed
    assert decision.hold_codes == ("no_content",)


def test_an_already_delivered_edition_holds(tmp_path: Path) -> None:
    _write_artifact(tmp_path, _artifact_payload())
    ledger = SendLedger(tmp_path / "send_log.json")
    first = _evaluate(tmp_path, ledger=ledger)
    assert first.content is not None
    ledger.start(
        first.content.key,
        revision=first.content.revision,
        audience="hannover-weekly-en",
        now=NOW,
    )
    ledger.complete(first.content.key, provider_message_id="campaign-1", now=NOW)

    decision = _evaluate(tmp_path, ledger=ledger)

    assert not decision.allowed
    assert decision.hold_codes == ("already_sent",)


def test_an_interrupted_send_of_the_same_content_may_resume(tmp_path: Path) -> None:
    _write_artifact(tmp_path, _artifact_payload())
    ledger = SendLedger(tmp_path / "send_log.json")
    first = _evaluate(tmp_path, ledger=ledger)
    assert first.content is not None
    ledger.start(
        first.content.key,
        revision=first.content.revision,
        audience="hannover-weekly-en",
        now=NOW,
    )

    decision = _evaluate(tmp_path, ledger=ledger)

    assert decision.allowed
    assert decision.hold_codes == ()


def test_an_interrupted_send_of_different_content_holds(tmp_path: Path) -> None:
    _write_artifact(tmp_path, _artifact_payload())
    ledger = SendLedger(tmp_path / "send_log.json")
    first = _evaluate(tmp_path, ledger=ledger)
    assert first.content is not None
    ledger.start(
        first.content.key,
        revision="0" * 64,
        audience="hannover-weekly-en",
        now=NOW,
    )

    decision = _evaluate(tmp_path, ledger=ledger)

    assert not decision.allowed
    assert decision.hold_codes == ("revision_conflict",)


def test_a_healthy_run_report_removes_the_approval_requirement(tmp_path: Path) -> None:
    _write_artifact(tmp_path, _artifact_payload())
    (tmp_path / "run_health.json").write_text(
        json.dumps({"status": "ok", "sources": [{"name": "Capitol", "status": "ok"}]}),
        encoding="utf-8",
    )

    decision = _evaluate(tmp_path)

    assert decision.allowed
    assert not decision.requires_approval


def test_a_failed_source_holds_the_edition(tmp_path: Path) -> None:
    _write_artifact(tmp_path, _artifact_payload())
    (tmp_path / "run_health.json").write_text(
        json.dumps(
            {
                "status": "degraded",
                "sources": [
                    {"name": "Capitol", "status": "ok"},
                    {"name": "Astor", "status": "failed"},
                ],
            }
        ),
        encoding="utf-8",
    )

    decision = _evaluate(tmp_path)

    assert not decision.allowed
    assert decision.hold_codes == ("run_unhealthy",)
    assert "Astor" in decision.holds[0].detail


def test_an_unreadable_health_report_holds_rather_than_assuming_health(
    tmp_path: Path,
) -> None:
    _write_artifact(tmp_path, _artifact_payload())
    (tmp_path / "run_health.json").write_text("not json", encoding="utf-8")

    decision = _evaluate(tmp_path)

    assert not decision.allowed
    assert decision.hold_codes == ("run_unhealthy",)


def test_all_applicable_holds_are_reported_together(tmp_path: Path) -> None:
    _write_artifact(tmp_path, _artifact_payload(with_events=False))
    (tmp_path / "run_health.json").write_text(
        json.dumps({"status": "failed", "sources": []}), encoding="utf-8"
    )

    decision = _evaluate(tmp_path, now=GENERATED_AT + timedelta(days=10))

    assert set(decision.hold_codes) == {"artifact_stale", "no_content", "run_unhealthy"}
