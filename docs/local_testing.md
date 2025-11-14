# KinoWeek Local Testing Guide

## Overview
This guide explains how to test the refactored KinoWeek scraper locally before moving to production containerization.

## Prerequisites
- Python 3.13+
- uv package manager
- Playwright browser binaries installed

## Installation & Setup

Setting up the project involves creating a virtual environment, installing dependencies, and downloading the necessary browser binaries for Playwright.

1.  **Create Environment & Install Dependencies**

    This project uses `uv` to manage dependencies. The following command will create a virtual environment, and install all required main and development packages from the `uv.lock` file.

    ```bash
    # Create the virtual environment and install all dependencies
    uv sync --dev
    ```

2.  **Install Playwright Browsers**

    Playwright requires separate browser binaries to function. After installing the Python packages, run the following command to download them:

    ```bash
    # Download and install browsers (Chromium, Firefox, WebKit)
    uv run playwright install
    ```
    *Note: This step is only required once, unless you update the Playwright package.*

3.  **Set Up Environment Variables**

    For notifications to work, you need to provide Telegram API credentials.

    ```bash
    # Copy the environment variable template
    cp .env.example .env
    ```
    Then, edit the `.env` file and add your `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

## Local Testing

### Method 1: Command Line Interface
```bash
# Run locally - saves results to output/ folder
python -m src.kinoweek.main --local

# Run with full Telegram integration (requires .env setup)
python -m src.kinoweek.main
```

### Method 2: Programmatic Usage
```python
from src.kinoweek.main import run_scraper

# Test locally (no Telegram)
success = run_scraper(local_only=True)

# Test with Telegram (requires env vars)
success = run_scraper(local_only=False)
```

### Method 3: Module-Specific Testing
```python
# Test scraping only
from src.kinoweek.scraper import scrape_movies
data = scrape_movies()

# Test message formatting only
from src.kinoweek.notifier import format_message, notify
message = format_message(data)
notify(data, local_only=True)
```

## Expected Output

When running locally (`--local` flag), the scraper creates:

### output/latest_message.txt
Contains the formatted Telegram message:
```
🎬 *Astor Grand Cinema - OV Schedule*

📅 *Mon 24.11*
🎭 *Wicked*
  • 19:30 (Cinema 10, 2D OV)
  • 16:45 (Cinema 10, 2D OmU)
```

### output/schedule.json
Contains raw structured data:
```json
{
  "Mon 24.11": {
    "Wicked": [
      "19:30 (Cinema 10, 2D OV)",
      "16:45 (Cinema 10, 2D OmU)"
    ]
  }
}
```

### kinoweek.log
Detailed execution logs with timestamps and status information.

## Testing Different Scenarios

### 1. Normal Operation
- Website loads successfully
- Movies are found and parsed
- Results saved to output/ folder
- Exit code: 0

### 2. No Movies Found
- Website loads but no movies available
- Empty JSON saved
- "No movies found" message created
- Exit code: 0 (successful run, just no data)

### 3. Network Issues
- Connection timeout or DNS failure
- Exception logged
- Exit code: 1 (failure)

### 4. Website Structure Changes
- Selectors don't match
- Warning logged, empty results returned
- Exit code: 0 (graceful handling)

## Validation Steps

1. **Check output files are created:**
   ```bash
   ls -la output/
   # Should show: latest_message.txt, schedule.json
   ```

2. **Verify message format:**
   ```bash
   head output/latest_message.txt
   # Should show properly formatted markdown with emojis
   ```

3. **Check JSON structure:**
   ```bash
   cat output/schedule.json
   # Should show valid JSON with expected structure
   ```

4. **Review logs:**
   ```bash
   tail -20 kinoweek.log
   # Should show INFO level messages without errors
   ```

## Integration Testing

### Test Suite
```bash
# Run all tests
pytest tests/ -v

# Run specific test categories
pytest tests/test_scraper.py::TestScrapeMovies -v
pytest tests/test_scraper.py::TestFormatMessage -v
pytest tests/test_scraper.py::TestSendTelegram -v
pytest tests/test_scraper.py::TestIntegration -v
```

### Mock Testing
The test suite includes comprehensive mocking for:
- Playwright browser automation
- Telegram API calls
- Environment variables
- Network requests

## Common Issues & Solutions

### Issue: Unicode Encoding Errors
**Symptom:** Emoji characters cause logging errors on Windows
**Solution:** Already fixed with UTF-8 encoding in log handlers

### Issue: Module Import Errors
**Symptom:** `ModuleNotFoundError: No module named 'src'`
**Solution:** Run from project root directory

### Issue: Playwright Browser Not Found
**Symptom:** Browser launch fails with an "Executable doesn't exist" error.
**Solution:** The browser binaries need to be installed. Run `uv run playwright install`.

### Issue: No Data Extracted
**Symptom:** Empty results despite website having content
**Solution:** Check website structure, selectors may need updating

## Next Steps for Production

After local testing is successful:

1. **Containerization Preparation:**
   - Docker configuration ready
   - Environment variables documented
   - Logging configuration optimized

2. **Production Deployment:**
   - Set up Telegram bot credentials in `.env`
   - Configure scheduling (cron/CI)
   - Monitor logs and error handling

3. **Monitoring & Maintenance:**
   - Watch `kinoweek.log` for issues
   -定期检查输出文件格式
   - Update selectors if website changes

## Development Workflow

```bash
# 1. Make changes to code
# 2. Test locally
python -m src.kinoweek.main --local

# 3. Run tests
pytest tests/ -v

# 4. Check output
ls output/ && head output/latest_message.txt

# 5. Review logs
tail -10 kinoweek.log

# 6. Ready for containerization
```

This local testing setup ensures the refactored code works correctly before moving to production deployment.