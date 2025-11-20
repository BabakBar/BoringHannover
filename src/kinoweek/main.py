"""
Main orchestration module for KinoWeek scraper.

This is a stateless, weekly script that fetches events from three sources:
1. Astor Grand Cinema (OV movies)
2. Staatstheater Hannover (Opera/Ballet)
3. Hannover-Concerts.de (Big events)
"""

import logging
import os
import sys
from typing import Dict, List

from kinoweek.scrapers import get_all_events
from kinoweek.notifier import notify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('kinoweek.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def validate_environment(local_only: bool) -> None:
    """
    Validate required environment variables at startup.

    Fails fast if environment variables are missing when sending to Telegram.

    Args:
        local_only: If True, skip validation (running in local test mode)

    Raises:
        SystemExit: If required environment variables are missing
    """
    if local_only:
        return

    missing = []
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        missing.append("TELEGRAM_BOT_TOKEN")
    if not os.getenv("TELEGRAM_CHAT_ID"):
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        logger.error(f"❌ Missing required environment variables: {', '.join(missing)}")
        logger.error("Set these in .env file or export them before running")
        sys.exit(1)


def run_scraper(local_only: bool = False) -> bool:
    """
    Run the complete scraping and notification workflow.

    This is the main orchestration function that:
    1. Fetches events from all three sources
    2. Categorizes them into "This Week" and "On The Radar"
    3. Sends a formatted Telegram message (or saves locally)

    Args:
        local_only: If True, save results locally instead of sending to Telegram

    Returns:
        True if successful, False otherwise
    """
    # Validate environment before proceeding
    validate_environment(local_only)

    try:
        logger.info("🚀 Starting KinoWeek scraper")
        logger.info("📡 Fetching events from all sources...")

        # Step 1: Gather all events
        events_data = get_all_events()

        # Log summary
        movies_count = len(events_data.get('movies_this_week', []))
        culture_count = len(events_data.get('culture_this_week', []))
        radar_count = len(events_data.get('big_events_radar', []))

        logger.info(f"📊 Summary:")
        logger.info(f"   - Movies (This Week): {movies_count}")
        logger.info(f"   - Culture (This Week): {culture_count}")
        logger.info(f"   - Big Events (Radar): {radar_count}")

        # Step 2: Send notification or save locally
        logger.info("📨 Sending notification...")
        success = notify(events_data, local_only=local_only)

        if success:
            logger.info("✅ Workflow completed successfully")
            return True
        else:
            logger.error("❌ Failed to send notification")
            return False

    except Exception as e:
        logger.error(f"💥 Workflow failed: {e}", exc_info=True)
        return False


def main() -> int:
    """
    Main entry point for the application.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="KinoWeek - Weekly event digest for Hannover",
        epilog="Run with --local flag to test without sending to Telegram"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Save results locally instead of sending to Telegram"
    )

    args = parser.parse_args()

    # Load environment variables from .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        logger.debug("python-dotenv not available, using system environment")

    success = run_scraper(local_only=args.local)

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
