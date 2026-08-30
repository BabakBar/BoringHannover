"""Durable send records: the only thing standing between a retry and a resend.

The ledger stores edition identity and delivery outcome. It never stores a
recipient address, a recipient count, or anything else that could identify a
subscriber — the email service provider owns the list.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Final, Literal


__all__ = [
    "EditionAlreadySent",
    "LedgerError",
    "RevisionConflict",
    "SendLedger",
    "SendRecord",
    "SendStatus",
]

logger = logging.getLogger(__name__)

SendStatus = Literal["in_progress", "completed", "failed"]

_LEDGER_VERSION: Final[int] = 1


class LedgerError(RuntimeError):
    """The ledger cannot be used safely."""


class EditionAlreadySent(LedgerError):
    """The edition has already been delivered; sending again would duplicate it."""


class RevisionConflict(LedgerError):
    """An interrupted send exists for different content than the one offered."""


@dataclass(frozen=True, slots=True)
class SendRecord:
    """One edition's delivery state."""

    edition_key: str
    revision: str
    audience: str
    status: SendStatus
    started_at: str
    completed_at: str | None = None
    provider_message_id: str | None = None
    error: str | None = None


class SendLedger:
    """A small JSON file recording which editions went out."""

    def __init__(self, path: str | Path) -> None:
        """Initialise the ledger.

        Args:
            path: JSON file holding the records. Created on first write.
        """
        self.path = Path(path)

    def _load(self) -> dict[str, SendRecord]:
        """Read all records, refusing to continue if the file is damaged."""
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            records = raw["records"]
            return {
                key: SendRecord(**value)
                for key, value in records.items()
                if isinstance(value, dict)
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            msg = (
                f"Send ledger {self.path} is unreadable; refusing to send and risk "
                f"a duplicate edition ({exc})"
            )
            raise LedgerError(msg) from exc

    def _save(self, records: dict[str, SendRecord]) -> None:
        """Write all records atomically."""
        payload = {
            "version": _LEDGER_VERSION,
            "records": {key: asdict(record) for key, record in records.items()},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            dir=self.path.parent,
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(json.dumps(payload, indent=2, ensure_ascii=False))
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, self.path)

    def record_for(self, edition_key: str) -> SendRecord | None:
        """Return the record for one edition, if any."""
        return self._load().get(edition_key)

    def is_completed(self, edition_key: str) -> bool:
        """True when the edition has already been delivered."""
        record = self.record_for(edition_key)
        return record is not None and record.status == "completed"

    def start(
        self,
        edition_key: str,
        *,
        revision: str,
        audience: str,
        now: datetime,
    ) -> SendRecord:
        """Claim an edition for sending, or resume an interrupted attempt.

        Args:
            edition_key: Canonical edition key.
            revision: Content revision being sent.
            audience: Provider-side list identifier, never a recipient address.
            now: Timestamp for the record.

        Returns:
            The in-progress record, existing or newly created.

        Raises:
            EditionAlreadySent: The edition was already delivered.
            RevisionConflict: An attempt is running for different content.
        """
        records = self._load()
        existing = records.get(edition_key)

        if existing is not None and existing.status == "completed":
            msg = (
                f"Edition {edition_key} was already delivered at "
                f"{existing.completed_at} (provider id {existing.provider_message_id})"
            )
            raise EditionAlreadySent(msg)

        if existing is not None and existing.status == "in_progress":
            if existing.revision != revision:
                msg = (
                    f"Edition {edition_key} has an unfinished send for revision "
                    f"{existing.revision[:12]}, but revision {revision[:12]} was "
                    "offered; resolve the interrupted send first"
                )
                raise RevisionConflict(msg)
            logger.info("Resuming interrupted send for %s", edition_key)
            return existing

        record = SendRecord(
            edition_key=edition_key,
            revision=revision,
            audience=audience,
            status="in_progress",
            started_at=now.isoformat(),
        )
        records[edition_key] = record
        self._save(records)
        return record

    def complete(
        self,
        edition_key: str,
        *,
        provider_message_id: str,
        now: datetime,
    ) -> SendRecord:
        """Mark an edition delivered.

        Raises:
            LedgerError: The edition was never started.
        """
        records = self._load()
        existing = records.get(edition_key)
        if existing is None:
            msg = f"Edition {edition_key} was not started; cannot complete it"
            raise LedgerError(msg)

        record = replace(
            existing,
            status="completed",
            completed_at=now.isoformat(),
            provider_message_id=provider_message_id,
            error=None,
        )
        records[edition_key] = record
        self._save(records)
        return record

    def fail(self, edition_key: str, *, reason: str, now: datetime) -> SendRecord:
        """Mark an attempt failed so the next run may retry it.

        Raises:
            LedgerError: The edition was never started.
        """
        records = self._load()
        existing = records.get(edition_key)
        if existing is None:
            msg = f"Edition {edition_key} was not started; cannot fail it"
            raise LedgerError(msg)

        record = replace(
            existing,
            status="failed",
            completed_at=now.isoformat(),
            error=reason,
        )
        records[edition_key] = record
        self._save(records)
        return record
