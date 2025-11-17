# KinoWeek Local Testing Guide

## Overview
This guide explains how to test the KinoWeek API-based scraper locally before deploying to production.

## Prerequisites
- Python 3.13+
- uv package manager

## Installation & Setup

1. **Install Dependencies**
   ```bash
   # Install all dependencies from uv.lock
   uv sync --dev
   ```

2. **Set Up Environment Variables** (Optional for local testing)
   ```bash
   # Copy the template
   cp .env.example .env

   # Edit .env with your Telegram credentials (only needed for Telegram testing)
   # TELEGRAM_BOT_TOKEN=your_bot_token_here
   # TELEGRAM_CHAT_ID=your_chat_id_here
   ```

## Local Testing

### Quick Test (No Telegram)
```bash
# Test locally - saves results to output/ folder
PYTHONPATH=src uv run python -m kinoweek.main --local
```

This will:
- Fetch movie data from the API
- Filter for OV (Original Version) movies only
- Save formatted message to `output/latest_message.txt`
- Save JSON data to `output/schedule.json`
- Create log file `kinoweek.log`

### Test with Telegram (Requires .env)
```bash
# Send actual Telegram notification
PYTHONPATH=src uv run python -m kinoweek.main
```

### Programmatic Testing
```python
from kinoweek.main import run_scraper
from kinoweek.scraper import scrape_movies
from kinoweek.notifier import format_message

# Test scraper only
data = scrape_movies()
print(f"Found {len(data)} dates with OV movies")

# Test full workflow locally
success = run_scraper(local_only=True)

# Test with Telegram
success = run_scraper(local_only=False)
```

## Expected Output

### output/latest_message.txt
Formatted Telegram message with OV movies and rich metadata:
```
🎬 *Astor Grand Cinema - OV Movies*
📊 45 films • 67 showtimes • 34 days

📅 *Mon 17.11.*
🎬 *Sneak Preview (OV)*
  _FSK18_
  ⏰ 20:30 (EN)

───────────────────────────────────
📅 *Tue 18.11.*
🎬 *Die Unfassbaren 3 - Now You See Me* (2025)
  _1h53m • FSK12_
  ⏰ 17:45 (EN)

🎬 *The Birth of Kitaro - The Mystery of Gegege* (2023)
  _1h44m • FSK16_
  ⏰ 20:30 (JP, UT:DE)

───────────────────────────────────
📅 *Fri 21.11.*
🎬 *Wicked: Teil 2* (2025)
  _2h17m • FSK12_
  ⏰ 16:45 (EN, UT:DE) • 19:50 (EN)
```

### output/schedule.json
Enhanced structured data with full metadata:
```json
{
  "Mon 17.11.": {
    "Sneak Preview (OV)": {
      "metadata": {
        "duration": 0,
        "rating": 18,
        "year": 0,
        "country": "",
        "genres": []
      },
      "showtimes": [
        {
          "time": "20:30",
          "version": "Sprache: Englisch",
          "datetime": "2025-11-17T20:30:00"
        }
      ]
    }
  },
  "Tue 18.11.": {
    "Die Unfassbaren 3 - Now You See Me": {
      "metadata": {
        "duration": 113,
        "rating": 12,
        "year": 2025,
        "country": "USA",
        "genres": [""]
      },
      "showtimes": [
        {
          "time": "17:45",
          "version": "Sprache: Englisch",
          "datetime": "2025-11-18T17:45:00"
        }
      ]
    }
  }
}
```

### Current Results
- **34 dates** with OV movies (chronologically sorted)
- **45 unique** OV films
- **67 OV showtimes** total
- **355 German-dubbed** showtimes filtered out
- **Full metadata** for each movie (duration, rating, year, country)

## Validation Steps

1. **Verify Output Files**
   ```bash
   ls -lh output/
   # Should show: latest_message.txt, schedule.json
   ```

2. **Check Message Format**
   ```bash
   head -30 output/latest_message.txt
   ```

3. **Validate JSON**
   ```bash
   cat output/schedule.json | python -m json.tool
   ```

4. **Review Logs**
   ```bash
   tail -20 kinoweek.log
   ```

## Testing Scenarios

### ✅ Normal Operation
- API responds successfully
- OV movies found and filtered
- Results saved to output/
- Exit code: 0

### ⚠️ No OV Movies Found
- API responds but no OV movies available
- Empty schedule saved
- "No movies found" message created
- Exit code: 0

### ❌ Network Issues
- API connection timeout or failure
- Exception logged with details
- Exit code: 1 (failure)

## OV Filtering Verification

The scraper filters for **Original Version** movies only:

**✅ Included (OV):**
- English language films (`Sprache: Englisch`)
- Japanese films with subtitles (`Sprache: Japanisch, Untertitel: Deutsch`)
- Italian operas with subtitles (`Sprache: Italienisch, Untertitel: Deutsch`)
- Any film with `Untertitel:` (German subtitles on original audio)

**❌ Excluded (Dubbed):**
- German dubbed films (`Sprache: Deutsch` without `Untertitel:`)

**Verify filtering:**
```bash
# Check that output only contains OV movies
grep "Sprache: Deutsch" output/schedule.json | grep -v "Untertitel"
# Should return nothing (all German-only dubbed versions filtered out)
```

## Running Tests

```bash
# Install package in editable mode
uv pip install -e .

# Run all tests
uv run pytest tests/ -v

# Run specific test class
uv run pytest tests/test_scraper.py::TestScrapeMovies -v

# Run with coverage
uv run pytest tests/ -v --cov=kinoweek
```

## Common Issues & Solutions

### Issue: Module Import Errors
**Symptom:** `ModuleNotFoundError: No module named 'kinoweek'`
**Solution:** Use `PYTHONPATH=src` or install with `uv pip install -e .`

### Issue: API Connection Failure
**Symptom:** `httpx.RequestError` or timeout
**Solution:** Check network connection, API may be temporarily down

### Issue: No OV Movies Found
**Symptom:** Empty output despite movies existing
**Solution:** Verify OV filtering logic, check API response format

## Development Workflow

```bash
# 1. Make code changes

# 2. Test locally
PYTHONPATH=src uv run python -m kinoweek.main --local

# 3. Verify output
head output/latest_message.txt
cat output/schedule.json | python -m json.tool | head -20

# 4. Run tests
uv pip install -e . && uv run pytest tests/ -v

# 5. Check logs
tail -15 kinoweek.log

# 6. Commit and push when ready
```

## Next Steps for Production

After successful local testing:

1. **Containerization** (Phase 5)
   - Create Dockerfile
   - Set up Docker Compose
   - Configure environment variables

2. **Deployment**
   - Deploy to Coolify or GitHub Actions
   - Set up weekly cron schedule
   - Configure Telegram bot credentials

3. **Monitoring**
   - Set up logging aggregation
   - Monitor for API changes
   - Track notification delivery

See `docs/progress.md` for implementation roadmap.
