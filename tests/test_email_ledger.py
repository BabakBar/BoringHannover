"""The send ledger is what makes a retry safe."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from boringhannover.constants import BERLIN_TZ
from boringhannover.newsletter.ledger import (
    EditionAlreadySent,
    LedgerError,
    RevisionConflict,
    SendLedger,
)


KEY = "hannover:2026-W35:en"
REVISION = "a" * 64
AUDIENCE = "hannover-weekly-en"
T0 = datetime(2026, 8, 27, 9, 0, tzinfo=BERLIN_TZ)
T1 = datetime(2026, 8, 27, 9, 5, tzinfo=BERLIN_TZ)


def _ledger(tmp_path: Path) -> SendLedger:
    return SendLedger(tmp_path / "send_log.json")


def test_an_unknown_edition_has_no_record(tmp_path: Path) -> None:
    assert _ledger(tmp_path).record_for(KEY) is None


def test_starting_a_send_persists_an_in_progress_record(tmp_path: Path) -> None:
    _ledger(tmp_path).start(KEY, revision=REVISION, audience=AUDIENCE, now=T0)

    record = _ledger(tmp_path).record_for(KEY)

    assert record is not None
    assert record.status == "in_progress"
    assert record.revision == REVISION
    assert record.audience == AUDIENCE
    assert record.started_at == T0.isoformat()
    assert record.completed_at is None


def test_completing_a_send_stores_the_provider_message_id(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.start(KEY, revision=REVISION, audience=AUDIENCE, now=T0)

    ledger.complete(KEY, provider_message_id="campaign-123", now=T1)

    record = _ledger(tmp_path).record_for(KEY)
    assert record is not None
    assert record.status == "completed"
    assert record.provider_message_id == "campaign-123"
    assert record.completed_at == T1.isoformat()
    assert ledger.is_completed(KEY)


def test_a_completed_edition_cannot_be_started_again(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.start(KEY, revision=REVISION, audience=AUDIENCE, now=T0)
    ledger.complete(KEY, provider_message_id="campaign-123", now=T1)

    with pytest.raises(EditionAlreadySent):
        ledger.start(KEY, revision=REVISION, audience=AUDIENCE, now=T1)


def test_an_interrupted_send_resumes_for_the_same_revision(tmp_path: Path) -> None:
    _ledger(tmp_path).start(KEY, revision=REVISION, audience=AUDIENCE, now=T0)

    resumed = _ledger(tmp_path).start(KEY, revision=REVISION, audience=AUDIENCE, now=T1)

    assert resumed.status == "in_progress"
    assert resumed.started_at == T0.isoformat(), "resume must not restart the record"


def test_an_interrupted_send_refuses_a_different_revision(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.start(KEY, revision=REVISION, audience=AUDIENCE, now=T0)

    with pytest.raises(RevisionConflict):
        ledger.start(KEY, revision="b" * 64, audience=AUDIENCE, now=T1)


def test_a_failed_send_can_be_retried(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.start(KEY, revision=REVISION, audience=AUDIENCE, now=T0)
    ledger.fail(KEY, reason="provider timeout", now=T1)

    assert ledger.record_for(KEY) is not None
    assert ledger.record_for(KEY).status == "failed"  # type: ignore[union-attr]

    retried = ledger.start(KEY, revision=REVISION, audience=AUDIENCE, now=T1)

    assert retried.status == "in_progress"


def test_completing_an_edition_that_never_started_is_refused(tmp_path: Path) -> None:
    with pytest.raises(LedgerError, match="not started"):
        _ledger(tmp_path).complete(KEY, provider_message_id="x", now=T1)


def test_a_corrupt_ledger_fails_closed_instead_of_resending(tmp_path: Path) -> None:
    path = tmp_path / "send_log.json"
    path.write_text("{ this is not json", encoding="utf-8")

    with pytest.raises(LedgerError, match="unreadable"):
        SendLedger(path).record_for(KEY)


def test_records_from_other_editions_are_preserved(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.start(KEY, revision=REVISION, audience=AUDIENCE, now=T0)
    ledger.complete(KEY, provider_message_id="campaign-123", now=T1)

    other = "hannover:2026-W36:en"
    ledger.start(other, revision="c" * 64, audience=AUDIENCE, now=T1)

    reloaded = SendLedger(tmp_path / "send_log.json")
    assert reloaded.is_completed(KEY)
    assert reloaded.record_for(other) is not None
