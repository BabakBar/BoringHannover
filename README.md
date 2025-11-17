# KinoWeek - Astor Kino Notifier

Automated API-based scraper for Astor Grand Cinema Hannover **Original Version (OV)** movie schedules with Telegram notifications.

## Features

- ✅ **Smart OV Filtering**: Automatically filters for Original Version movies only
- 🚀 **Fast API Access**: Direct API calls (no browser automation needed)
- 📱 **Telegram Integration**: Weekly notifications with formatted movie schedules
- 🧪 **Local Testing Mode**: Test without sending Telegram messages
- 🎯 **Accurate**: Filters out 85% of German-dubbed content, keeping only OV films
- 📊 **Rich Metadata**: Displays duration, FSK ratings, release year, and country
- 📅 **Chronological Sorting**: Shows dates in actual order, not alphabetically
- 💎 **Polished Output**: Professional, compact formatting optimized for Telegram

## Quick Start

```bash
# Install dependencies
uv sync --dev

# Set up environment variables
cp .env.example .env
# Edit .env with your Telegram bot token and chat ID

# Test locally (saves to output/ directory)
PYTHONPATH=src uv run python -m kinoweek.main --local

# Run with Telegram notifications
PYTHONPATH=src uv run python -m kinoweek.main
```

## Environment Variables

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
LOG_LEVEL=INFO  # Optional
```

## Development

```bash
# Run tests (package installation required)
uv pip install -e .
uv run pytest tests/ -v

# Test the scraper directly
PYTHONPATH=src uv run python -c "from kinoweek.scraper import scrape_movies; print(scrape_movies())"

# Check output files
cat output/latest_message.txt
cat output/schedule.json
```

## How It Works

1. **Fetches** movie data from `backend.premiumkino.de` API
2. **Extracts** rich metadata: duration, FSK ratings, release year, country, and genres
3. **Filters** for Original Version (OV) movies:
   - Includes: English, Japanese, Italian, Spanish, Russian films
   - Includes: Original versions with German subtitles
   - Excludes: German-dubbed movies (355 of 419 total showtimes filtered out)
4. **Sorts** chronologically by date for easy planning
5. **Formats** into polished, compact Telegram message with metadata
6. **Sends** weekly notification or saves locally for testing

## Output Example

```
🎬 *Astor Grand Cinema - OV Movies*
📊 45 films • 67 showtimes • 34 days

📅 *Mon 17.11.*
🎬 *Sneak Preview (OV)*
  _FSK18_
  ⏰ 20:30 (EN)

📅 *Tue 18.11.*
🎬 *Die Unfassbaren 3 - Now You See Me* (2025)
  _1h53m • FSK12_
  ⏰ 17:45 (EN)

🎬 *The Birth of Kitaro - The Mystery of Gegege* (2023)
  _1h44m • FSK16_
  ⏰ 20:30 (JP, UT:DE)
```

## Results

Current output: **67 OV showtimes** across **45 unique films** and **34 dates**

## Deployment

Ready for deployment using Coolify or GitHub Actions with scheduled cron jobs (weekly execution).

See `docs/progress.md` for implementation details and `docs/local_testing.md` for testing guide.
