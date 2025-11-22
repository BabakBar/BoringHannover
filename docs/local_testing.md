# Local Development Guide

## Backend Setup

### 1. Install Dependencies
```bash
# Install all dependencies from uv.lock
uv sync --dev
```

### 2. Set Up Environment Variables (Optional for local testing)
```bash
# Copy the template
cp .env.example .env

# Edit .env with your Telegram credentials (only needed for Telegram testing)
# TELEGRAM_BOT_TOKEN=your_bot_token_here
# TELEGRAM_CHAT_ID=your_chat_id_here
```

## Running the Scraper

### Quick Test (No Telegram)
```bash
# Test locally - saves results to output/ folder
uv run kinoweek --local
```

This generates:
- `output/events.json` - Full event data
- `output/web_events.json` - Frontend-optimized data
- `output/weekly_digest.md` - Human-readable digest
- `output/movies.csv`, `output/concerts.csv` - CSV exports

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

---

## Frontend Setup

The frontend is located in the `web/` directory and uses Astro + TailwindCSS.

### 1. Install Dependencies
```bash
cd web
bun install
```

### 2. Run Development Server
```bash
bun run dev
# Opens at http://localhost:4321
```

### 3. Build for Production
```bash
bun run build
# Outputs to web/dist/
```

### 4. Preview Production Build
```bash
bun run preview
```

## Full Local Workflow

To test the complete flow (scraper → frontend):

```bash
# 1. Run the scraper to generate data
uv run kinoweek --local

# 2. Start the frontend (reads from output/web_events.json)
cd web && bun run dev
```

The frontend will automatically load data from `../output/web_events.json` if it exists, otherwise it falls back to mock data.

## Troubleshooting

### Frontend shows mock data instead of real data
- Ensure you've run the scraper first (`--local` flag)
- Check that `output/web_events.json` exists
- Restart the dev server after generating new data

### Build fails with type errors
```bash
# Check TypeScript types
cd web && bun run astro check
```