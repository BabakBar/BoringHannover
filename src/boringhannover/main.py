"""Main orchestration module for BoringHannover.

Entry point for the weekly event aggregation workflow:
1. Fetch events from all configured sources
2. Categorize into movies and "On The Radar"
3. Export formatted data to multiple output formats
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import NoReturn

from boringhannover.aggregator import fetch_all_events
from boringhannover.github_sync import should_sync, sync_to_github
from boringhannover.notifier import notify

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
            logging.FileHandler("boringhannover.log", encoding="utf-8"),
        ],
    )


logger = logging.getLogger(__name__)


# =============================================================================
# Main Workflow
# =============================================================================


def run(*, local: bool = False) -> bool:
    """Execute the complete scraping and export workflow.

    This is the main orchestration function that:
    1. Fetches events from movies (Astor) and concerts (venues)
    2. Categorizes them into movies and "On The Radar"
    3. Exports data to multiple formats (CSV, JSON, Markdown)
    4. Syncs to GitHub (if configured) to trigger frontend rebuild

    Args:
        local: If True, runs in local/dev mode (no GitHub sync).

    Returns:
        True if workflow completed successfully.
    """
    try:
        logger.info("Starting BoringHannover scraper")
        if local:
            logger.info("Running in local mode (GitHub sync disabled)")
        logger.info("Fetching events from all sources...")

        # Step 1: Gather all events
        events_data = fetch_all_events()

        # Log summary
        movies_count = len(events_data.get("movies_this_week", []))
        radar_count = len(events_data.get("big_events_radar", []))

        logger.info("Summary:")
        logger.info("  - Movies: %d", movies_count)
        logger.info("  - Concerts (On Radar): %d", radar_count)

        # Step 2: Export to files
        logger.info("Exporting data...")
        from typing import cast  # noqa: PLC0415

        from boringhannover.notifier import EventsData  # noqa: PLC0415

        success = notify(cast("EventsData", events_data))

        if not success:
            logger.error("Failed to export data")
            return False

        # Step 3: Sync data to GitHub (if configured)
        if (not local) and should_sync():
            logger.info("Syncing data to GitHub...")
            sync_success = sync_to_github("output/web_events.json")
            if sync_success:
                logger.info("GitHub sync completed - frontend rebuild triggered")
            else:
                logger.warning("GitHub sync failed - frontend will show stale data")

        logger.info("Workflow completed successfully")

    except Exception:
        logger.exception("Workflow failed")
        return False
    else:
        return True


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
        description="BoringHannover - Weekly event digest for Hannover",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run locally (save outputs to ./output and skip GitHub sync)",
    )
    return parser.parse_args()


def _load_environment() -> None:
    """Load environment variables from .env file if available."""
    try:
        from dotenv import load_dotenv  # noqa: PLC0415

        load_dotenv()
    except ImportError:
        logger.debug("python-dotenv not available, using system environment")


def main() -> NoReturn:
    """Main entry point for the application.

    Loads environment, runs the workflow, and exits with appropriate status code.
    """
    _configure_logging()
    args = _parse_args()
    _load_environment()

    success = run(local=bool(getattr(args, "local", False)))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
