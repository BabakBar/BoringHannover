"""Scraper module for Astor Kino website using direct API calls."""

import logging
from typing import Dict, List
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

def scrape_movies() -> Dict[str, Dict[str, List[str]]]:
    """
    Scrape movie schedules from Astor Grand Cinema Hannover's API.
    """
    api_url = "https://backend.premiumkino.de/v1/de/hannover/program"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json; charset=utf-8",
        "Referer": "https://hannover.premiumkino.de/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    }
    
    schedule_data: Dict[str, Dict[str, List[str]]] = {}

    try:
        logger.info(f"Fetching data from {api_url}")
        with httpx.Client() as client:
            response = client.get(api_url, headers=headers)
            response.raise_for_status()
            data = response.json()

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
            date_str = begin_dt.strftime("%a %d.%m.")
            time_str = begin_dt.strftime("%H:%M")

            version = perf.get('language', 'Unknown Version')
            
            showtime_str = f"{time_str} ({version})"

            if date_str not in schedule_data:
                schedule_data[date_str] = {}
            
            if title not in schedule_data[date_str]:
                schedule_data[date_str][title] = []
            
            schedule_data[date_str][title].append(showtime_str)

    except httpx.RequestError as e:
        logger.error(f"HTTP request failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        raise

    return schedule_data