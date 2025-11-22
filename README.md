# KinoWeek - Weekly Event Digest for Hannover

A stateless, weekly script that aggregates events in Hannover from curated sources and delivers a formatted digest.

## Quick Start

```bash
# Install dependencies
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env with your Telegram bot token and chat ID

# Test locally (saves to output/ directory)
uv run kinoweek --local

# Run with Telegram notifications
uv run kinoweek
```

## Message Format

The script generates a compact weekly digest with two sections:

```
*Hannover Week 47*

*Movies (This Week)*

*Fri 21.11.*
  *Chainsaw Man - The Movie: Reze Arc (2025)*
  _1h41m | FSK16_
  22:50 (JP, UT:DE)

*Sat 22.11.*
  *Wicked: Teil 2 (2025)*
  _2h17m | FSK12_
  13:45 (EN)
  *Wicked: Teil 2 (2025)*
  _2h17m | FSK12_
  19:50 (EN)

*On The Radar*
  *LUCIANO*
  Sa, 29. Nov | 20:00 @ ZAG Arena
  *BÖHSE ONKELZ*
  So, 30. Nov | 19:30 @ ZAG Arena
  *Architects*
  Di, 13. Jan 2026 | 20:00 @ Swiss Life Hall
```

## Architecture

### Modular Plugin-Based Sources

KinoWeek uses a **plugin-based architecture** for event sources. Each source is a self-contained module that registers itself automatically:

1. **Astor Grand Cinema** (OV Movies)
   - Source: Direct API access to `backend.premiumkino.de`
   - Filter: Original version movies only (no German dubs)
   - Includes: EN, JP, IT, ES, RU + films with German subtitles
   - Timeframe: Next 7 days

2. **Concert Venues** (Live Music)
   - **Large Venues**: ZAG Arena, Swiss Life Hall, Capitol Hannover
   - **Cultural Centers**: Faust, Pavillon, MusikZentrum
   - **Clubs**: Béi Chéz Heinz
   - Content: Concerts, festivals, live music events
   - Timeframe: Events beyond 7 days (on the radar)

### How It Works

```
┌─────────────────┐
│   Run Weekly    │  (Monday, via cron)
│   (Stateless)   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│   Source Registry           │
│   (Auto-discovered plugins) │
├─────────────────────────────┤
│  • astor_hannover (cinema)  │
│  • bei_chez_heinz (concert) │
│  • capitol_hannover (concert)│
│  • faust_hannover (concert) │
│  • musikzentrum (concert)   │
│  • pavillon (concert)       │
│  • swiss_life_hall (concert)│
│  • zag_arena (concert)      │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│   Aggregator                │
│   • Fetch from all sources  │
│   • Categorize by time      │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│   Notifier                  │
│   • Format message          │
│   • Send to Telegram        │
└─────────────────────────────┘
```

## Configuration

### Source Configuration (TOML)

Sources are configured in `src/kinoweek/sources.toml`:

```toml
[sources.zag_arena]
enabled = true
source_type = "concert"
display_name = "ZAG Arena"
url = "https://www.zag-arena-hannover.de/veranstaltungen/"
max_events = 15

[sources.zag_arena.metadata]
address = "Expo Plaza 7, 30539 Hannover"
```

### Adding a New Source

Create a module in `sources/` and use the `@register_source` decorator:

```python
# sources/concerts/new_venue.py
from kinoweek.sources import BaseSource, register_source

@register_source("new_venue")
class NewVenueSource(BaseSource):
    source_name = "New Venue"
    source_type = "concert"

    def fetch(self) -> list[Event]:
        # Your implementation
        ...
```

No other code changes needed - the source is auto-discovered!

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

# Test the full workflow locally
uv run kinoweek --local

# Check output files
cat output/latest_message.txt
cat output/events.json
```

## Project Structure

```
src/kinoweek/
├── __init__.py       # Package exports and lazy imports
├── models.py         # Event dataclass (unified data structure)
├── config.py         # Global settings and constants
├── sources.toml      # Source configuration (TOML)
├── aggregator.py     # Central orchestration for all sources
├── sources/          # Plugin-based source modules
│   ├── __init__.py   # Registry & autodiscovery
│   ├── base.py       # BaseSource ABC + @register_source
│   ├── cinema/       # Cinema sources
│   │   └── astor.py  # Astor Grand Cinema
│   └── concerts/     # Concert venue sources
│       ├── bei_chez_heinz.py
│       ├── capitol.py
│       ├── faust.py
│       ├── musikzentrum.py
│       ├── pavillon.py
│       ├── swiss_life_hall.py
│       └── zag_arena.py
├── notifier.py       # Telegram notification & orchestration
├── formatting.py     # Message formatting helpers & language mappings
├── output.py         # OutputManager & movie grouping logic
├── exporters.py      # JSON, Markdown, and archive exports
├── csv_exporters.py  # CSV export implementations
├── main.py           # CLI entry point
└── _archive/         # Archived legacy code
    └── scrapers.py   # Old monolithic scraper (replaced by sources/)

tests/
└── test_scraper.py   # 26 unit and integration tests

output/
├── latest_message.txt  # Formatted Telegram message
├── events.json         # Enhanced JSON with metadata
├── movies.csv          # Movie showtimes (one row per showtime)
├── movies_grouped.csv  # Grouped movies (one row per film)
├── concerts.csv        # Concert events
├── weekly_digest.md    # Human-readable Markdown digest
└── archive/            # Weekly snapshots (YYYY-WXX.json)
```

## Deployment

### Weekly Cron Job

```bash
# Run every Monday at 9 AM
0 9 * * 1 cd /path/to/kinoweek && uv run python -m kinoweek.main
```

### GitHub Actions

Ready for GitHub Actions with scheduled workflows.

## Current Status

**8 Sources Active** (1 cinema + 7 concert venues):

| Source | Type | Events | Notes |
|--------|------|--------|-------|
| Astor Grand Cinema | Cinema | ~56 | OV movies via API |
| Béi Chéz Heinz | Club | ~3 | Punk/indie/metal |
| Capitol Hannover | Large | ~10 | HC-Kartenleger |
| Faust | Cultural | ~12 | Livemusik category |
| MusikZentrum | Medium | ~16 | JSON-LD data |
| Pavillon | Cultural | ~20 | World music focus |
| Swiss Life Hall | Large | ~10 | HC-Kartenleger |
| ZAG Arena | Arena | ~9 | WPEM plugin |

All 26 tests passing. End-to-end workflow verified.

## Roadmap

1. ~~Lean MVP with stateless architecture~~ ✅
2. ~~Configure all concert venue scrapers~~ ✅ (7 venues)
3. ~~Web frontend (Astro + TailwindCSS)~~ ✅ MVP complete
4. Deploy web frontend to Coolify
5. Schedule weekly cron job / GitHub Actions
6. Add ticket links to concert output

## Philosophy

> "A side project that ships is worth more than a perfect system that never launches."

This script prioritizes:
- **Shipping over perfection** - Works reliably, iterates based on usage
- **Simplicity over features** - No database, no state, just run it
- **Signal over noise** - Two curated sources, OV filtering
- **Reliability over cleverness** - Graceful failures, clear logs

See `docs/architecture.md` for detailed design decisions.
