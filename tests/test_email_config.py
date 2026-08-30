"""Configuration is read from the environment and fails closed on bad input."""

from __future__ import annotations

from pathlib import Path

from boringhannover.newsletter.config import (
    DEFAULT_ARTIFACT_PATH,
    NewsletterConfig,
)


def test_defaults_apply_without_any_environment() -> None:
    config = NewsletterConfig.from_env({})

    assert config.artifact_path == DEFAULT_ARTIFACT_PATH
    assert config.city_id == "hannover"
    assert config.locale == "en"
    assert config.provider == "preview"


def test_environment_overrides_are_parsed() -> None:
    config = NewsletterConfig.from_env(
        {
            "NEWSLETTER_ARTIFACT_PATH": "data/web_events.json",
            "NEWSLETTER_LEDGER_PATH": "data/send_log.json",
            "NEWSLETTER_CITY_ID": "berlin",
            "NEWSLETTER_LOCALE": "de",
            "NEWSLETTER_AUDIENCE": "berlin-weekly-de",
        }
    )

    assert config.artifact_path == Path("data/web_events.json")
    assert config.ledger_path == Path("data/send_log.json")
    assert config.city_id == "berlin"
    assert config.locale == "de"
    assert config.audience == "berlin-weekly-de"


def test_an_empty_health_path_disables_the_health_check() -> None:
    config = NewsletterConfig.from_env({"NEWSLETTER_HEALTH_PATH": ""})

    assert config.health_path is None


def test_an_unset_health_path_keeps_the_default() -> None:
    config = NewsletterConfig.from_env({})

    assert config.health_path is not None
