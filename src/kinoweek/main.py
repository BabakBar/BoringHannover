"""Main orchestration module for KinoWeek.

Entry point for the weekly event aggregation workflow:
1. Fetch events from all configured sources
2. Categorize into "This Week" and "On The Radar"
3. Send formatted digest via Telegram (or save locally for development)
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import NoReturn

from kinoweek.notifier import notify
from kinoweek.scrapers import fetch_all_events

__all__ = ["main", "run"]


# =============================================================================
# Logging Configuration
# =============================================================================


def _configure_logging() -> None:
    """Configure logging for the application.

    Sets up both console and file logging with consistent formatting.
    """
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("kinoweek.log", encoding="utf-8"),
        ],
    )


logger = logging.getLogger(__name__)


# =============================================================================
# Environment Validation
# =============================================================================


def _validate_environment(*, local_only: bool) -> None:
    """Validate required environment variables.

    Performs fail-fast validation of Telegram credentials when running
    in production mode.

    Args:
        local_only: Skip validation if True (development mode).

    Raises:
        SystemExit: If required environment variables are missing.
    """
    import os

    if local_only:
        return

    missing: list[str] = []

    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        missing.append("TELEGRAM_BOT_TOKEN")
    if not os.getenv("TELEGRAM_CHAT_ID"):
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        logger.error(
            "Missing required environment variables: %s",
            ", ".join(missing),
        )
        logger.error("Set these in .env file or export them before running")
        sys.exit(1)


# =============================================================================
# Main Workflow
# =============================================================================


def run(*, local_only: bool = False) -> bool:
    """Execute the complete scraping and notification workflow.

    This is the main orchestration function that:
    1. Fetches events from all three sources
    2. Categorizes them into "This Week" and "On The Radar"
    3. Sends a formatted Telegram message (or saves locally)

    Args:
        local_only: Save results locally instead of sending to Telegram.

    Returns:
        True if workflow completed successfully.
    """
    _validate_environment(local_only=local_only)

    try:
        logger.info("Starting KinoWeek scraper")
        logger.info("Fetching events from all sources...")

        # Step 1: Gather all events
        events_data = fetch_all_events()

        # Log summary
        movies_count = len(events_data.get("movies_this_week", []))
        culture_count = len(events_data.get("culture_this_week", []))
        radar_count = len(events_data.get("big_events_radar", []))

        logger.info("Summary:")
        logger.info("  - Movies (This Week): %d", movies_count)
        logger.info("  - Culture (This Week): %d", culture_count)
        logger.info("  - Big Events (Radar): %d", radar_count)

        # Step 2: Send notification or save locally
        logger.info("Sending notification...")
        success = notify(events_data, local_only=local_only)

        if success:
            logger.info("Workflow completed successfully")
            return True

        logger.error("Failed to send notification")
        return False

    except Exception:
        logger.exception("Workflow failed")
        return False


# Backward compatibility alias
run_scraper = run


# =============================================================================
# CLI Entry Point
# =============================================================================


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="KinoWeek - Weekly event digest for Hannover",
        epilog="Run with --local flag to test without sending to Telegram",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Save results locally instead of sending to Telegram",
    )
    return parser.parse_args()


def _load_environment() -> None:
    """Load environment variables from .env file if available."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        logger.debug("python-dotenv not available, using system environment")


def main() -> NoReturn:
    """Main entry point for the application.

    Parses arguments, loads environment, runs the workflow,
    and exits with appropriate status code.
    """
    _configure_logging()
    args = _parse_args()
    _load_environment()

    success = run(local_only=args.local)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
