"""
Scrapers for all three KinoWeek sources.

This module provides stateless scrapers for:
1. Astor Grand Cinema (OV movies)
2. Staatstheater Hannover (Opera/Ballet via iCal)
3. Concert venues (Big events)
"""

import logging
from typing import List
from datetime import datetime, timedelta
import httpx
from ics import Calendar
from bs4 import BeautifulSoup

from kinoweek.models import Event
from kinoweek.config import (
    ASTOR_API_URL,
    STAATSTHEATER_ICAL_URL,
    CONCERT_SOURCES,
    IGNORE_KEYWORDS,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

logger = logging.getLogger(__name__)


def should_filter_event(title: str) -> bool:
    """
    Check if event should be filtered out based on keywords.

    Args:
        title: Event title to check

    Returns:
        True if event should be filtered out, False otherwise
    """
    title_lower = title.lower()
    return any(keyword.lower() in title_lower for keyword in IGNORE_KEYWORDS)


def is_original_version(language: str) -> bool:
    """
    Determine if a showtime is in original version (OV).

    OV movies are those NOT dubbed in German. This includes:
    - Movies in English, Japanese, Italian, Spanish, Russian, etc.
    - Movies with German subtitles (indicated by "Untertitel:")

    NOT OV:
    - Movies with "Sprache: Deutsch" without subtitles (German dubs)

    Args:
        language: Language string from the API (e.g., "Sprache: Englisch")

    Returns:
        True if this is an original version showing, False otherwise
    """
    if not language:
        return False

    # If it's German language, only include if it has subtitles
    if "Deutsch" in language:
        return "Untertitel:" in language

    # All other languages (English, Japanese, Italian, etc.) are original versions
    return True


def scrape_astor_movies() -> List[Event]:
    """
    Scrape movie schedules from Astor Grand Cinema Hannover's API.

    Returns OV (original version) movies only, converted to Event objects.

    Returns:
        List of Event objects with category="movie"
    """
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json; charset=utf-8",
        "Referer": "https://hannover.premiumkino.de/",
        "User-Agent": USER_AGENT,
    }

    events = []

    try:
        logger.info(f"Fetching Astor movies from {ASTOR_API_URL}")
        with httpx.Client() as client:
            response = client.get(ASTOR_API_URL, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()

        # Build genre mapping
        genres_map = {genre['id']: genre['name'] for genre in data.get('genres', [])}

        # Build movie metadata
        movies = {movie['id']: movie for movie in data.get('movies', [])}
        performances = data.get('performances', [])

        for perf in performances:
            movie_id = perf.get('movieId')
            if movie_id not in movies:
                continue

            movie = movies[movie_id]
            title = movie.get('name')

            begin_str = perf.get('begin')
            if not begin_str:
                continue

            begin_dt = datetime.fromisoformat(begin_str)
            version = perf.get('language', 'Unknown Version')

            # Filter for Original Version (OV) movies only
            if not is_original_version(version):
                logger.debug(f"Skipping non-OV: {title} ({version})")
                continue

            # Build metadata
            metadata = {
                'duration': movie.get('minutes', 0),
                'rating': movie.get('rating', 0),
                'year': movie.get('year', 0),
                'country': movie.get('country', ''),
                'genres': [genres_map.get(gid, '') for gid in movie.get('genreIds', [])],
                'language': version,
            }

            # Create Event
            event = Event(
                title=title,
                date=begin_dt,
                venue="Astor Grand Cinema",
                url="https://hannover.premiumkino.de/",
                category="movie",
                metadata=metadata,
            )
            events.append(event)

        logger.info(f"Found {len(events)} OV movie showtimes from Astor")

    except httpx.RequestError as e:
        logger.error(f"Astor API request failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Astor scraping failed: {e}")
        raise

    return events


def scrape_staatstheater_events(start_date: datetime, end_date: datetime) -> List[Event]:
    """
    Scrape opera/ballet events from Staatstheater Hannover via iCal feed.

    Note: The iCal feed may not be publicly available. This function will
    gracefully fail and return an empty list if the feed is not accessible.

    Args:
        start_date: Start of date range to fetch
        end_date: End of date range to fetch

    Returns:
        List of Event objects with category="culture"
    """
    events = []

    try:
        logger.info(f"Fetching Staatstheater events from {STAATSTHEATER_ICAL_URL}")
        with httpx.Client() as client:
            response = client.get(STAATSTHEATER_ICAL_URL, timeout=REQUEST_TIMEOUT, follow_redirects=True)
            response.raise_for_status()
            calendar = Calendar(response.text)

        for ical_event in calendar.events:
            # Convert ics datetime to Python datetime
            event_date = ical_event.begin.datetime

            # Filter by date range
            if not (start_date <= event_date <= end_date):
                continue

            # Filter by keywords
            if should_filter_event(ical_event.name):
                logger.debug(f"Filtering out: {ical_event.name}")
                continue

            # Extract metadata
            metadata = {
                'description': ical_event.description or '',
                'location': ical_event.location or '',
            }

            event = Event(
                title=ical_event.name,
                date=event_date,
                venue=ical_event.location or "Staatstheater Hannover",
                url=ical_event.url or "https://www.staatstheater-hannover.de/",
                category="culture",
                metadata=metadata,
            )
            events.append(event)

        logger.info(f"Found {len(events)} culture events from Staatstheater")

    except httpx.RequestError as e:
        logger.error(f"Staatstheater iCal request failed: {e}")
        # Don't raise - allow other scrapers to continue
        logger.warning("Continuing without Staatstheater events")
    except Exception as e:
        logger.error(f"Staatstheater scraping failed: {e}")
        logger.warning("Continuing without Staatstheater events")

    return events


def scrape_hannover_concerts(limit: int = 5) -> List[Event]:
    """
    Scrape big concert/event listings from configured concert venues.

    This scraper fetches the "next big things" - major concerts and events
    that are worth knowing about months in advance.

    Note: Currently disabled by default. Enable specific venues in config.py

    Args:
        limit: Maximum number of upcoming events to return (default: 5)

    Returns:
        List of Event objects with category="radar"
    """
    events = []

    # Check if any sources are enabled
    enabled_sources = [s for s in CONCERT_SOURCES if s.get('enabled', False)]
    if not enabled_sources:
        logger.info("No concert sources enabled (configure in config.py)")
        return events

    for source in enabled_sources:
        try:
            logger.info(f"Fetching concerts from {source['name']}: {source['url']}")
            with httpx.Client() as client:
                response = client.get(source['url'], timeout=REQUEST_TIMEOUT, follow_redirects=True)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

            # Find event listings
            # Note: This selector may need adjustment based on actual site structure
            # Common patterns: div.event, article.concert, li.event-item, etc.
            event_items = soup.select('.event-item, .concert-item, article.event, div.event')

            if not event_items:
                # Fallback: try finding by semantic HTML
                event_items = soup.select('article, .card, .listing-item')
                logger.debug(f"Using fallback selector, found {len(event_items)} items")

            for item in event_items[:limit]:
                try:
                    # Extract title
                    title_elem = item.select_one('h2, h3, .title, .event-title, .concert-title')
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)

                    # Filter by keywords
                    if should_filter_event(title):
                        logger.debug(f"Filtering out: {title}")
                        continue

                    # Extract date
                    date_elem = item.select_one('.date, .event-date, time, .datetime')
                    if not date_elem:
                        # Try data-date attribute
                        date_str = item.get('data-date')
                        if not date_str:
                            continue
                    else:
                        date_str = date_elem.get('datetime') or date_elem.get_text(strip=True)

                    # Parse date (try multiple formats)
                    event_date = None
                    for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"]:
                        try:
                            event_date = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue

                    if not event_date:
                        logger.debug(f"Could not parse date: {date_str}")
                        continue

                    # Extract venue
                    venue_elem = item.select_one('.venue, .location, .event-venue')
                    venue = venue_elem.get_text(strip=True) if venue_elem else source['name']

                    # Extract URL
                    link_elem = item.select_one('a')
                    event_url = link_elem.get('href') if link_elem else source['url']
                    if event_url.startswith('/'):
                        event_url = f"{source['url'].rstrip('/')}{event_url}"

                    event = Event(
                        title=title,
                        date=event_date,
                        venue=venue,
                        url=event_url,
                        category="radar",
                        metadata={},
                    )
                    events.append(event)

                except Exception as e:
                    logger.debug(f"Error parsing concert item: {e}")
                    continue

            logger.info(f"Found {len(events)} events from {source['name']}")

        except httpx.RequestError as e:
            logger.error(f"{source['name']} request failed: {e}")
            logger.warning(f"Continuing without {source['name']} events")
        except Exception as e:
            logger.error(f"{source['name']} scraping failed: {e}")
            logger.warning(f"Continuing without {source['name']} events")

    return events


def get_all_events() -> dict:
    """
    Fetch all events from all sources and categorize them.

    Returns:
        Dictionary with keys:
        - 'movies_this_week': List of movie events in next 7 days
        - 'culture_this_week': List of culture events in next 7 days
        - 'big_events_radar': List of upcoming big events (next 5)
    """
    today = datetime.now()
    next_week = today + timedelta(days=7)

    # Gather from all sources
    logger.info("Fetching events from all sources...")

    movies = scrape_astor_movies()
    culture = scrape_staatstheater_events(today, next_week)
    radar = scrape_hannover_concerts(limit=5)

    # Filter movies to this week only
    movies_this_week = [m for m in movies if m.is_this_week()]

    # Culture events are already filtered by date range
    culture_this_week = culture

    # Sort all lists by date
    movies_this_week.sort(key=lambda x: x.date)
    culture_this_week.sort(key=lambda x: x.date)
    radar.sort(key=lambda x: x.date)

    return {
        'movies_this_week': movies_this_week,
        'culture_this_week': culture_this_week,
        'big_events_radar': radar,
    }
