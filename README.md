# KinoWeek - Weekly Event Digest for Hannover

A stateless, weekly script that aggregates cultural events in Hannover from three curated sources.

## The Lean MVP Philosophy

**Complexity kills side projects.** KinoWeek is intentionally simple:
- **No Database**: Stateless - just run it weekly
- **No Deduplication**: Simple is better than perfect
- **No Real-time Alerts**: One message per week, every Monday
- **Three Quality Sources**: High signal, low noise

## Features

- 🎬 **Movies (This Week)**: OV (original version) movies at Astor Grand Cinema
- 🎭 **Culture (This Week)**: Opera, ballet, and theater at Staatstheater Hannover
- 🔭 **On The Radar**: Big upcoming concerts and events (6+ months ahead)
- 📱 **Telegram Integration**: Weekly digest delivered to your phone
- 🧪 **Local Testing Mode**: Test without sending messages
- 🔧 **Easy Configuration**: All URLs and settings in one file

## Quick Start

```bash
# Install dependencies
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env with your Telegram bot token and chat ID

# Test locally (saves to output/ directory)
PYTHONPATH=src uv run python -m kinoweek.main --local

# Run with Telegram notifications
PYTHONPATH=src uv run python -m kinoweek.main
```

## Message Format

The script generates a compact weekly digest with two sections:

```
*Hannover Week 47* 🇩🇪

🎬 *Movies (This Week)*

📅 *Fri 21.11.*
• *Wicked: Teil 2* (2025)
  _2h17m • FSK12_
  ⏰ 16:45 (EN, UT:DE)

🎭 *Culture (This Week)*
• *La Bohème* (Opera)
  Fri 19:30 @ Staatstheater

🔭 *On The Radar (Big Events)*
• *Sting*
  12. Dec @ ZAG Arena
• *Hans Zimmer*
  15. Mar 2026 @ ZAG Arena
```

## Architecture

### The Three Sources

1. **Astor Grand Cinema** (OV Movies)
   - Source: Direct API access to `backend.premiumkino.de`
   - Filter: Original version movies only (no German dubs)
   - Includes: EN, JP, IT, ES, RU + films with German subtitles
   - Timeframe: Next 7 days

2. **Staatstheater Hannover** (Culture)
   - Source: iCal feed (when available) or HTML scraping
   - Content: Opera, ballet, theater, symphony
   - Filter: Excludes workshops, tours, children's events
   - Timeframe: Next 7 days

3. **Concert Venues** (Big Events)
   - Sources: ZAG Arena, Swiss Life Hall, Capitol (configurable)
   - Content: Major concerts and shows
   - Purpose: "Planning horizon" for big events
   - Timeframe: Next 5 upcoming events (can be months ahead)

### How It Works

```
┌─────────────────┐
│   Run Weekly    │  (Monday, via cron)
│   (Stateless)   │
└────────┬────────┘
         │
         ├──► Fetch Astor Movies     ─┐
         ├──► Fetch Staatstheater    ─┤ Parallel
         └──► Fetch Concert Events   ─┘
                    │
                    ▼
         ┌──────────────────┐
         │  Filter & Sort   │
         │  • This Week     │
         │  • On The Radar  │
         └────────┬─────────┘
                  │
                  ▼
         ┌────────────────┐
         │  Format Message│
         │  (2 Sections)  │
         └────────┬───────┘
                  │
                  ▼
         ┌────────────────┐
         │Send to Telegram│
         └────────────────┘
```

## Configuration

Edit `src/kinoweek/config.py` to customize:

```python
# Keywords to filter out (noise reduction)
IGNORE_KEYWORDS = [
    "Führung",
    "Einführung",
    "Kindertheater",
    "Workshop",
]

# Concert sources (enable/disable as needed)
CONCERT_SOURCES = [
    {
        "name": "ZAG Arena",
        "url": "https://www.zagarena.de/events/",
        "enabled": False,  # Change to True when configured
    },
]
```

## Environment Variables

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
LOG_LEVEL=INFO  # Optional
```

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Test individual scrapers
PYTHONPATH=src uv run python -c "
from kinoweek.scrapers import scrape_astor_movies
print(f'Found {len(scrape_astor_movies())} movie showtimes')
"

# Check output files
cat output/latest_message.txt
cat output/events.json
```

## Project Structure

```
src/kinoweek/
├── models.py      # Event dataclass (unified data structure)
├── config.py      # All URLs and settings
├── scrapers.py    # Three scrapers (Astor, Staatstheater, Concerts)
├── notifier.py    # Message formatting + Telegram API
└── main.py        # Orchestration + CLI

output/
├── latest_message.txt  # Formatted message
└── events.json         # Structured event data
```

## Deployment

### Weekly Cron Job

```bash
# Run every Monday at 9 AM
0 9 * * 1 cd /path/to/kinoweek && PYTHONPATH=src uv run python -m kinoweek.main
```

### Coolify / Docker

Ready for containerized deployment with scheduled execution.

## Current Status

- ✅ **Astor Movies**: Fully working (29 OV showtimes this week)
- 🚧 **Staatstheater**: iCal feed needs URL fix (returns 404)
- 🚧 **Concert Venues**: Disabled by default (configure URLs in config.py)

The script gracefully handles missing sources - it works perfectly with just Astor for now, and you can add the other sources when their URLs are configured.

## Roadmap

1. ✅ Lean MVP with stateless architecture
2. 🚧 Fix Staatstheater iCal URL or switch to HTML scraping
3. 🚧 Configure concert venue URLs
4. 📅 Schedule weekly cron job
5. 🎯 Monitor and adjust keyword filters

## Philosophy

> "A side project that ships is worth more than a perfect system that never launches."

This script prioritizes:
- **Shipping over perfection** - Works with one source, adds more later
- **Simplicity over features** - No database, no state, just run it
- **Signal over noise** - Three curated sources, keyword filtering
- **Reliability over cleverness** - Graceful failures, clear logs

See `docs/architecture.md` for detailed design decisions.
