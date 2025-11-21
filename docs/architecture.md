# Architecture Document: KinoWeek

## Executive Summary

KinoWeek is a stateless, weekly event aggregator for Hannover that fetches OV movies and concerts from multiple sources and delivers a formatted digest via Telegram. The system uses modern Python (3.13+) with a **plugin-based source architecture**, type hints, and comprehensive testing.

## System Overview

```
┌─────────────────┐    ┌──────────────────────────────┐    ┌─────────────────┐
│   Scheduler     │───▶│   Source Registry            │───▶│   Notifier      │
│  (Cron/Manual)  │    │   (Plugin-based, auto-disco) │    │  (Telegram)     │
└─────────────────┘    └──────────────────────────────┘    └─────────────────┘
         │                           │                              │
         ▼                           ▼                              ▼
┌─────────────────┐    ┌──────────────────────────────┐    ┌─────────────────┐
│   Weekly Job    │    │  sources/cinema/astor.py     │    │   Bot API       │
│   (Stateless)   │    │  sources/concerts/zag_arena  │    │   + Multi-format│
└─────────────────┘    │  sources/concerts/swiss_life │    │     Output      │
                       │  sources/concerts/capitol    │    └─────────────────┘
                       └──────────────────────────────┘
```

## Component Architecture

### 1. Data Model (`models.py`)

**Purpose**: Unified event structure for all sources

```python
@dataclass(slots=True, kw_only=True)
class Event:
    title: str
    date: datetime
    venue: str
    url: str
    category: Literal["movie", "culture", "radar"]
    metadata: dict[str, str | int | list[str]] = field(default_factory=dict)
```

**Features**:
- `slots=True` for memory efficiency
- `kw_only=True` for explicit construction
- `Literal` type for category validation
- Helper methods: `format_date_short()`, `format_time()`, `is_this_week()`

### 2. Configuration (`config.py`)

**Purpose**: Centralized settings with type safety

**Key Components**:
- `ASTOR_API_URL`: Movie API endpoint
- `CONCERT_VENUES`: Tuple of `VenueConfig` TypedDicts with selectors
- `GERMAN_MONTH_MAP`: Date parsing support
- `Final` constants for immutability

### 3. Source Registry (`sources/`)

**Architecture**: Plugin-based with decorator registration and autodiscovery

```python
# sources/base.py
class BaseSource(ABC):
    source_name: ClassVar[str]   # Human-readable name
    source_type: ClassVar[str]   # "cinema", "concert", "theater"
    enabled: ClassVar[bool] = True
    max_events: ClassVar[int | None] = None

    @abstractmethod
    def fetch(self) -> list[Event]: ...

# Decorator for automatic registration
@register_source("source_id")
class MySource(BaseSource):
    ...
```

**Autodiscovery**: Sources are automatically discovered on import via `pkgutil.iter_modules()`.

**Registry Functions**:
- `get_all_sources()`: Returns all registered sources
- `get_sources_by_type(type)`: Filter by category
- `get_source(name)`: Get specific source class

**Implementations**:

#### AstorSource (`sources/cinema/astor.py`)
- **Source**: `backend.premiumkino.de` JSON API
- **Filter**: Original Version only (no German dubs)
- **Output**: Events with `category="movie"`
- **Metadata**: duration, rating, year, country, genres, language, poster, trailer

```python
# OV Detection Logic in sources/base.py
def is_original_version(language: str) -> bool:
    if "Deutsch" in language:
        return "Untertitel:" in language  # German subs = OV
    return True  # All other languages are OV
```

#### Concert Sources (`sources/concerts/`)
Each venue has its own module:
- `zag_arena.py`: ZAG Arena (WPEM selectors)
- `swiss_life_hall.py`: Swiss Life Hall (HC-Kartenleger)
- `capitol.py`: Capitol Hannover (HC-Kartenleger)

**Venue-Specific Parsing**:
- ZAG Arena: `.wpem-event-layout-wrapper` containers
- Swiss Life Hall / Capitol: `.hc-card-link-wrapper` cards

### 4. Aggregator (`aggregator.py`)

**Purpose**: Central orchestration for all registered sources

```python
def fetch_all_events() -> dict[str, list[Event]]:
    """Fetch from all registered and enabled sources."""
    for name, source_cls in get_all_sources().items():
        source = source_cls()
        if source.enabled:
            events = source.fetch()
            # Categorize by type and time...
```

### 5. Notifier & Formatting (`notifier.py`, `formatting.py`)

**Purpose**: Message formatting and delivery (split into two modules)

**notifier.py - Orchestration**:
- `format_message()`: Creates Telegram-ready message
- `send_telegram_message()`: Posts to Telegram Bot API
- `save_to_file()`: JSON and text backup
- `save_all_formats()`: Delegates to exporters for full export
- `notify()`: Orchestrates local/remote delivery

**formatting.py - Message Helpers**:
- Language abbreviations: EN, JP, DE, IT, ES, RU, FR, KR, ZH
- Venue abbreviations
- `format_duration()`: Convert minutes to "2h17m"
- `format_movie_metadata()`: Extract and format movie details
- `format_concert_date()`: German date formatting ("Sa, 29. Nov")
- `format_movies_section()`: Format "Movies (This Week)" block
- `format_radar_section()`: Format "On The Radar" block

**Message Sections**:
1. **Movies (This Week)**: Grouped by date, with metadata
2. **On The Radar**: Concerts with German day names

**Date Formatting**:
```python
# German day/month names for concert display
_GERMAN_DAYS = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
_GERMAN_MONTHS = {1: "Jan", 2: "Feb", ..., 12: "Dez"}

# Output: "Sa, 29. Nov | 20:00 @ ZAG Arena"
```

### 5b. Output & Exports (`output.py`, `exporters.py`, `csv_exporters.py`)

**Purpose**: Multi-format data export (split into three modules)

**output.py - Data Structures & Manager**:
- `Showtime` dataclass: Single movie showing
- `GroupedMovie` dataclass: Movie with consolidated showtimes
- `group_movies_by_film()`: Consolidate showtimes per unique film
- `OutputManager`: Manages all export formats
- `export_all_formats()`: Convenience function

**exporters.py - JSON, Markdown, Archives**:
- `export_enhanced_json()`: Structured JSON with metadata & stats
- `export_markdown_digest()`: Human-readable weekly digest
- `archive_weekly_data()`: Create timestamped weekly snapshot

**csv_exporters.py - CSV Exports**:
- `export_movies_csv()`: Flat list (one row per showtime)
- `export_movies_grouped_csv()`: One row per unique film
- `export_concerts_csv()`: Concert events with metadata

### 6. Main Orchestration (`main.py`)

**Entry Point**: `main()` → `run(local_only=False)`

**Workflow**:
1. Configure logging (console + file)
2. Validate environment (Telegram credentials)
3. Call `fetch_all_events()`
4. Call `notify(events_data, local_only=...)`
5. Exit with appropriate status code

## Data Flow

### Event Aggregation

```
AstorMovieScraper.fetch()     ─┐
                               ├─► fetch_all_events()
ConcertVenueScraper.fetch()   ─┘
         │
         ▼
┌────────────────────────────────────┐
│ Categorization:                    │
│ • movies_this_week (next 7 days)   │
│ • big_events_radar (beyond 7 days) │
└────────────────────────────────────┘
         │
         ▼
    dict[str, list[Event]]
```

### Output Data Structure

```python
{
    "movies_this_week": [Event(...), ...],
    "big_events_radar": [Event(...), ...],
}
```

### JSON Export Format

```json
{
  "movies_this_week": [
    {
      "title": "Wicked: Teil 2",
      "date": "2025-11-22T13:45:00",
      "venue": "Astor Grand Cinema",
      "url": "https://hannover.premiumkino.de/",
      "category": "movie",
      "metadata": {
        "duration": 137,
        "rating": 12,
        "year": 2025,
        "language": "Sprache: Englisch"
      }
    }
  ],
  "big_events_radar": [
    {
      "title": "LUCIANO",
      "date": "2025-11-29T20:00:00",
      "venue": "ZAG Arena",
      "url": "https://www.zag-arena-hannover.de/...",
      "category": "radar",
      "metadata": {"time": "20:00"}
    }
  ]
}
```

## Error Handling

### Graceful Degradation
- Individual scraper failures don't crash the workflow
- Empty results are handled gracefully
- Network errors logged with context

### Retry Strategy (Future Enhancement)
- Exponential backoff for transient failures
- Maximum retry attempts configurable

## Testing Strategy

### Test Coverage (26 tests)

1. **Event Model Tests** (6 tests)
   - Creation, metadata, date formatting, week detection

2. **Scraper Tests** (7 tests)
   - Source names, API parsing, OV filtering, empty responses

3. **Notifier Tests** (10 tests)
   - Message formatting, sections, Telegram API, local mode

4. **Integration Tests** (3 tests)
   - Full workflow with mocked scrapers

### Running Tests

```bash
uv run python -m pytest tests/ -v
```

## Performance

### Current Metrics
- **Execution Time**: ~6 seconds (network dependent)
- **Memory Usage**: < 100MB
- **API Calls**: 4 total (1 Astor + 3 venues)

### Optimizations
- Single API call for all Astor data
- Connection reuse via httpx.Client context manager
- In-memory processing (no database)

## Security

### Secrets Management
- Environment variables for Telegram credentials
- `.env` file support via python-dotenv
- No hardcoded secrets

### Network Security
- HTTPS only
- Standard User-Agent header
- Timeout configuration (30s)

## Deployment Options

### 1. Local Cron Job
```bash
0 9 * * 1 cd /path/to/kinoweek && uv run python -m kinoweek.main
```

### 2. GitHub Actions
```yaml
on:
  schedule:
    - cron: '0 9 * * 1'  # Monday 9 AM UTC
```

### 3. Container (Docker/Coolify)
- Scheduled task execution
- Environment variable injection

## Future Enhancements

### Potential Improvements
1. **Movie Deduplication**: Group showtimes per film
2. **Ticket Links**: Include URLs in concert output
3. **Genre Display**: Show movie genres
4. **Additional Venues**: Easy to add via config

### Extension Points
- New scrapers: Extend `BaseScraper`
- New notification channels: Add alongside Telegram
- Database persistence: Add for historical analysis

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Language | Python 3.13+ | Modern features, type hints |
| HTTP Client | httpx | Async-ready, clean API |
| HTML Parsing | BeautifulSoup4 | Robust HTML extraction |
| Package Manager | uv | Fast, modern tooling |
| Testing | pytest | Comprehensive test suite |
| Linting | ruff | Fast, comprehensive |
| Type Checking | mypy (strict) | Type safety |

## File Structure

```
KinoWeek/
├── src/kinoweek/
│   ├── __init__.py       # Package with lazy imports
│   ├── models.py         # Event dataclass
│   ├── config.py         # Global settings and constants
│   ├── sources.toml      # Source configuration (TOML)
│   ├── aggregator.py     # Central orchestration
│   ├── sources/          # Plugin-based source modules
│   │   ├── __init__.py   # Registry & autodiscovery
│   │   ├── base.py       # BaseSource ABC + @register_source
│   │   ├── cinema/
│   │   │   └── astor.py  # Astor Grand Cinema
│   │   └── concerts/
│   │       ├── zag_arena.py
│   │       ├── swiss_life_hall.py
│   │       └── capitol.py
│   ├── notifier.py       # Telegram notification & orchestration
│   ├── formatting.py     # Message formatting helpers & language mappings
│   ├── output.py         # OutputManager & movie grouping logic
│   ├── exporters.py      # JSON, Markdown, and archive exports
│   ├── csv_exporters.py  # CSV export implementations
│   ├── main.py           # CLI entry point
│   └── _archive/         # Archived legacy code
│       └── scrapers.py   # Old monolithic scraper (replaced by sources/)
├── tests/
│   └── test_scraper.py   # 26 tests
├── docs/
│   ├── architecture.md   # This document
│   └── extension-strategy.md
├── output/               # Generated files
├── pyproject.toml        # Modern Python config
└── README.md             # Quick start guide
```

## Conclusion

KinoWeek demonstrates a clean, maintainable architecture for a weekly aggregation system:
- **Modular design** with clear separation of concerns
- **Type safety** with modern Python features
- **Comprehensive testing** for reliability
- **Graceful degradation** for robustness
- **Simple deployment** with multiple options

The stateless design keeps complexity low while delivering a useful weekly digest.
