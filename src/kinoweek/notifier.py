"""
Notifier module for message formatting and Telegram notifications.

Formats events into a two-section message:
1. "This Week" - Movies and Culture happening in the next 7 days
2. "On The Radar" - Big events coming up in the future
"""

import os
import json
import logging
from typing import List, Dict
from datetime import datetime
import httpx

from kinoweek.models import Event

logger = logging.getLogger(__name__)


def format_message(events_data: dict) -> str:
    """
    Format events into a two-section Telegram message.

    Args:
        events_data: Dictionary with keys:
            - 'movies_this_week': List[Event]
            - 'culture_this_week': List[Event]
            - 'big_events_radar': List[Event]

    Returns:
        Formatted message string in Telegram Markdown format
    """
    movies = events_data.get('movies_this_week', [])
    culture = events_data.get('culture_this_week', [])
    radar = events_data.get('big_events_radar', [])

    # Get current week number
    week_num = datetime.now().isocalendar()[1]

    message_lines = [
        f"*Hannover Week {week_num}* 🇩🇪\n"
    ]

    # Section 1: Movies (This Week)
    message_lines.append("🎬 *Movies (This Week)*")
    if movies:
        # Group by date for better readability
        movies_by_date = {}
        for event in movies:
            date_key = event.format_date_short()
            if date_key not in movies_by_date:
                movies_by_date[date_key] = []
            movies_by_date[date_key].append(event)

        for date_str, date_events in movies_by_date.items():
            message_lines.append(f"\n📅 *{date_str}*")
            for event in date_events:
                title = event.title
                if event.metadata.get('year'):
                    title += f" ({event.metadata['year']})"

                # Format metadata
                meta_parts = []
                duration = event.metadata.get('duration', 0)
                if duration:
                    hours = duration // 60
                    mins = duration % 60
                    if hours > 0:
                        meta_parts.append(f"{hours}h{mins}m" if mins else f"{hours}h")
                    else:
                        meta_parts.append(f"{mins}m")

                rating = event.metadata.get('rating', 0)
                if rating:
                    meta_parts.append(f"FSK{rating}")

                # Format language (make compact)
                language = event.metadata.get('language', '')
                lang_display = (language
                                .replace("Sprache: ", "")
                                .replace("Untertitel: ", "UT:")
                                .replace("Englisch", "EN")
                                .replace("Japanisch", "JP")
                                .replace("Italienisch", "IT")
                                .replace("Spanisch", "ES")
                                .replace("Russisch", "RU")
                                .replace("Deutsch", "DE"))

                time_str = event.date.strftime("%H:%M")

                # Build movie line
                message_lines.append(f"• *{title}*")
                if meta_parts:
                    message_lines.append(f"  _{' • '.join(meta_parts)}_")
                message_lines.append(f"  ⏰ {time_str} ({lang_display})")
    else:
        message_lines.append("_No OV movies this week_")

    message_lines.append("")  # Empty line

    # Section 2: Culture (This Week)
    message_lines.append("🎭 *Culture (This Week)*")
    if culture:
        for event in culture:
            time_str = event.format_time()  # "Fri 19:30"
            venue_short = event.venue.replace("Staatstheater Hannover", "Staatstheater")
            message_lines.append(f"• *{event.title}*")
            message_lines.append(f"  {time_str} @ {venue_short}")
    else:
        message_lines.append("_No culture events this week_")

    message_lines.append("")  # Empty line

    # Section 3: On The Radar (Big Events)
    message_lines.append("🔭 *On The Radar (Big Events)*")
    if radar:
        for event in radar:
            date_str = event.format_date_long()  # "12. Dec" or "15. Mar 2026"
            venue_short = event.venue
            # Shorten common venue names
            venue_short = (venue_short
                          .replace("ZAG Arena", "ZAG")
                          .replace("Swiss Life Hall", "SLH")
                          .replace("Expo Plaza", "Expo"))
            message_lines.append(f"• *{event.title}*")
            message_lines.append(f"  {date_str} @ {venue_short}")
    else:
        message_lines.append("_No big events on radar_")

    message = "\n".join(message_lines).strip()

    # Ensure message doesn't exceed Telegram limits
    if len(message) > 4096:
        message = message[:4050] + "\n\n... (truncated)"

    return message


def send_telegram(message: str) -> bool:
    """
    Send message via Telegram Bot API.

    Args:
        message: Message to send

    Returns:
        True if successful, False otherwise
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        with httpx.Client() as client:
            response = client.post(url, json=data, timeout=30)
            response.raise_for_status()

            result = response.json()
            if result.get("ok"):
                logger.info("Telegram message sent successfully")
                return True
            else:
                logger.error(f"Telegram API error: {result}")
                return False

    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def save_to_file(message: str, events_data: dict, output_dir: str = "output") -> None:
    """
    Save message and event data to local files for development testing.

    Args:
        message: Formatted message string
        events_data: Dictionary of event lists
        output_dir: Output directory path
    """
    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Save formatted message
        message_file = os.path.join(output_dir, "latest_message.txt")
        with open(message_file, 'w', encoding='utf-8') as f:
            f.write(message)

        # Convert events to JSON-serializable format
        def event_to_dict(event: Event) -> dict:
            return {
                'title': event.title,
                'date': event.date.isoformat(),
                'venue': event.venue,
                'url': event.url,
                'category': event.category,
                'metadata': event.metadata or {},
            }

        json_data = {
            'movies_this_week': [event_to_dict(e) for e in events_data.get('movies_this_week', [])],
            'culture_this_week': [event_to_dict(e) for e in events_data.get('culture_this_week', [])],
            'big_events_radar': [event_to_dict(e) for e in events_data.get('big_events_radar', [])],
        }

        # Save structured event data as JSON
        json_file = os.path.join(output_dir, "events.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Results saved to {output_dir}/")

    except Exception as e:
        logger.error(f"Failed to save results: {e}")


def notify(events_data: dict, local_only: bool = False) -> bool:
    """
    Send notification via Telegram or save locally for development.

    Args:
        events_data: Dictionary of event lists
        local_only: If True, save to files instead of sending to Telegram

    Returns:
        True if successful, False otherwise
    """
    try:
        # Format message
        message = format_message(events_data)

        if local_only:
            # Save to local files for development testing
            save_to_file(message, events_data)
            logger.info("Results saved locally (development mode)")
            print("\n" + message + "\n")  # Also print to console
            return True
        else:
            # Send via Telegram
            success = send_telegram(message)
            if success:
                # Also save a backup
                save_to_file(message, events_data, "backup")
            return success

    except Exception as e:
        logger.error(f"Notification failed: {e}")
        return False
