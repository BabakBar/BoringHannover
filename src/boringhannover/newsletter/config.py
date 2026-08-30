"""Configuration for the weekly email digest.

Everything here is read from environment variables so secrets (provider API
keys, subscriber lists) never enter this repository or any generated artifact.
Defaults are development-safe: artifact, ledger and preview paths point into
``output/``, which is generated at runtime and must not be committed.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final


__all__ = [
    "DEFAULT_ARTIFACT_PATH",
    "DEFAULT_AUDIENCE",
    "DEFAULT_CITY_ID",
    "DEFAULT_HEALTH_PATH",
    "DEFAULT_LEDGER_PATH",
    "DEFAULT_LOCALE",
    "DEFAULT_PREVIEW_DIR",
    "DEFAULT_PROVIDER",
    "DEFAULT_UNSUBSCRIBE_URL",
    "NewsletterConfig",
]

DEFAULT_ARTIFACT_PATH: Final[Path] = Path("output/web_events.json")
DEFAULT_LEDGER_PATH: Final[Path] = Path("output/newsletter_send_log.json")
DEFAULT_HEALTH_PATH: Final[Path] = Path("output/run_health.json")
DEFAULT_PREVIEW_DIR: Final[Path] = Path("output/newsletter_preview")
DEFAULT_CITY_ID: Final[str] = "hannover"
DEFAULT_LOCALE: Final[str] = "en"
DEFAULT_AUDIENCE: Final[str] = "hannover-weekly-en"
DEFAULT_PROVIDER: Final[str] = "preview"
DEFAULT_UNSUBSCRIBE_URL: Final[str] = (
    "https://boringhannover.de/newsletter/unsubscribe/"
)


@dataclass(frozen=True, slots=True)
class NewsletterConfig:
    """Operational settings for building and delivering one edition."""

    artifact_path: Path
    ledger_path: Path
    health_path: Path | None
    preview_dir: Path
    city_id: str
    locale: str
    audience: str
    unsubscribe_url: str
    provider: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> NewsletterConfig:
        """Build the configuration from environment variables.

        Args:
            environ: Mapping to read instead of ``os.environ`` (for tests).

        Returns:
            A frozen configuration. Empty strings are treated as unset, so a
            health path can be disabled with ``NEWSLETTER_HEALTH_PATH=``.
        """
        env = os.environ if environ is None else environ

        def _get(name: str, default: str) -> str:
            value = env.get(name)
            return value if value else default

        health_raw = env.get("NEWSLETTER_HEALTH_PATH")
        health_path: Path | None
        if health_raw:
            health_path = Path(health_raw)
        elif "NEWSLETTER_HEALTH_PATH" in env:
            health_path = None
        else:
            health_path = DEFAULT_HEALTH_PATH

        return cls(
            artifact_path=Path(
                _get("NEWSLETTER_ARTIFACT_PATH", str(DEFAULT_ARTIFACT_PATH))
            ),
            ledger_path=Path(_get("NEWSLETTER_LEDGER_PATH", str(DEFAULT_LEDGER_PATH))),
            health_path=health_path,
            preview_dir=Path(_get("NEWSLETTER_PREVIEW_DIR", str(DEFAULT_PREVIEW_DIR))),
            city_id=_get("NEWSLETTER_CITY_ID", DEFAULT_CITY_ID),
            locale=_get("NEWSLETTER_LOCALE", DEFAULT_LOCALE),
            audience=_get("NEWSLETTER_AUDIENCE", DEFAULT_AUDIENCE),
            unsubscribe_url=_get("NEWSLETTER_UNSUBSCRIBE_URL", DEFAULT_UNSUBSCRIBE_URL),
            provider=_get("NEWSLETTER_PROVIDER", DEFAULT_PROVIDER),
        )
