# technical_context.md

## METADATA
| Field | Value |
|-------|-------|
| last_updated | 2025-11-23 |
| updated_by | AI assistant |
| change_trigger | Security & Accessibility audit implementation |
| version | 1.1.0 |
| project_name | KinoWeek (BoringHannover) |

---

## FILE_STRUCTURE

```
KinoWeek/
├── src/kinoweek/           # Python backend
│   ├── __init__.py
│   ├── main.py             # CLI entry point
│   ├── config.py           # Constants, URLs, selectors
│   ├── models.py           # Event dataclass
│   ├── aggregator.py       # Source orchestration
│   ├── notifier.py         # Telegram + local output
│   ├── formatting.py       # Message formatting helpers
│   ├── output.py           # OutputManager, movie grouping
│   ├── exporters.py        # JSON, Markdown, Archive exports
│   ├── csv_exporters.py    # CSV exports
│   ├── sources/            # Plugin-based scrapers
│   │   ├── __init__.py     # Registry + autodiscovery
│   │   ├── base.py         # BaseSource ABC, helpers
│   │   ├── cinema/
│   │   │   └── astor.py    # Astor Grand Cinema (JSON API)
│   │   └── concerts/
│   │       ├── bei_chez_heinz.py   # Béi Chéz Heinz
│   │       ├── capitol.py          # Capitol Hannover
│   │       ├── faust.py            # Kulturzentrum Faust
│   │       ├── musikzentrum.py     # MusikZentrum
│   │       ├── pavillon.py         # Pavillon
│   │       ├── swiss_life_hall.py  # Swiss Life Hall
│   │       └── zag_arena.py        # ZAG Arena
│   └── _archive/           # Legacy code (deprecated)
├── web/                    # Astro frontend
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── components/
│       ├── data/
│       │   ├── types.ts    # TypeScript interfaces
│       │   ├── loader.ts   # JSON data loader
│       │   └── mock.ts     # Mock data fallback
│       ├── layouts/
│       ├── pages/
│       └── styles/
├── tests/
│   └── test_scraper.py     # 26 pytest tests
├── docs/
│   ├── architecture.md
│   └── frontend-plan.md
├── output/                 # Generated files (gitignored)
├── pyproject.toml          # Python config
└── .env.example
```

---

## ARCHITECTURE

### Pattern
Stateless event aggregator. Plugin-based scraper registry with autodiscovery.

### Components

| Component | File | Purpose |
|-----------|------|---------|
| Entry Point | `main.py` | CLI, workflow orchestration |
| Config | `config.py` | URLs, selectors, constants, rate limits |
| Data Model | `models.py` | `Event` dataclass with validation |
| Sanitization | `sanitize.py` | Input sanitization (nh3-based) |
| Aggregator | `aggregator.py` | Fetch from all sources |
| Source Registry | `sources/__init__.py` | `@register_source` decorator |
| Base Source | `sources/base.py` | `BaseSource` ABC |
| Notifier | `notifier.py` | Telegram API, file output |
| Formatting | `formatting.py` | Language abbrevs, date formatting |
| Output Manager | `output.py` | Multi-format export orchestration |
| Exporters | `exporters.py`, `csv_exporters.py` | JSON/MD/CSV generation |

### Data Flow
```
Scheduler (cron/manual)
    ↓
main.run(local_only=bool)
    ↓
aggregator.fetch_all_events()
    ↓
sources/*.fetch() → list[Event]
    ↓
Categorization:
  - movies_this_week (next 7 days, category="movie")
  - big_events_radar (>7 days, category="radar")
    ↓
notifier.notify()
    ↓
├── Telegram Bot API (production)
└── Local files: output/ (development)
```

### Background Jobs
None. Stateless execution. Scheduled via external cron/GitHub Actions.

### Deployment Options
- Local cron: `0 9 * * 1 uv run kinoweek --local`
- GitHub Actions: scheduled workflow
- Docker/Coolify: container with env vars

---

## SCRAPING_LOGIC

### Source Registry

| Source ID | Class | Type | Method | URL | Max Events |
|-----------|-------|------|--------|-----|------------|
| `astor_hannover` | `AstorSource` | cinema | JSON API | `backend.premiumkino.de/v1/de/hannover/program` | unlimited |
| `zag_arena` | `ZAGArenaSource` | concert | HTML (WPEM) | `zag-arena-hannover.de/veranstaltungen/` | 15 |
| `swiss_life_hall` | `SwissLifeHallSource` | concert | HTML (HC-Kartenleger) | `swisslife-hall.de/events/` | 15 |
| `capitol_hannover` | `CapitolSource` | concert | HTML (HC-Kartenleger) | `capitol-hannover.de/events/` | 15 |
| `bei_chez_heinz` | `BeiChezHeinzSource` | concert | HTML (custom) | `beichezheinz.de/programm` | 20 |
| `erhardt_cafe` | `ErhardtCafeSource` | concert | Wix Events + Static | `erhardt.cafe/events` | 20 |
| `faust_hannover` | `FaustSource` | concert | HTML (REDAXO) | `kulturzentrum-faust.de/veranstaltungen.html` (multi-category) | 40 |
| `pavillon` | `PavillonSource` | concert | HTML (custom) | `pavillon-hannover.de/programm` | 20 |
| `musikzentrum` | `MusikZentrumSource` | concert | JSON-LD | `musikzentrum-hannover.de/veranstaltungen/` | 20 |

### Parsing Details

**Astor Cinema (JSON API)**
- Endpoint returns: `{genres: [], movies: [], performances: []}`
- Build lookup maps: `genres_map[id] → name`, `movies_map[id] → movie`
- Filter: `is_original_version(language)` - skip German dubs
- OV logic: German only if has subtitles (`"Untertitel:" in language`)
- Rich metadata: duration, rating, year, country, genres, poster, trailer, cast

**ZAG Arena (WordPress Event Manager)**
- Selectors: `.wpem-event-layout-wrapper`, `.wpem-heading-text`, `.wpem-event-date-time-text`
- Date parsing: `parse_german_date()` handles "Fr, 22.11.2025 19:30"

**Swiss Life Hall / Capitol (HC-Kartenleger)**
- Same structure: `a.hc-card-link-wrapper`, `time` element
- Date format: "AB22NOV2025" → `parse_venue_date()`
- Sold out detection: `.sold-out`, `.ausverkauft` classes, text content

**Béi Chéz Heinz (Custom)**
- Filter: `_Konzert_` category only
- Date from URL: `/programm/2025-11-22/...`
- Time: Parse "Beginn: 20.00 Uhr" or "Einlass: 19.00 Uhr" + 1h

**Erhardt Café (Wix Events + Google Calendar)**
- Hybrid approach: tries Wix Events JSON extraction (often returns 0 events)
- Falls back to static Google Calendar data (manually updated in source code)
- Event types: games, karaoke, quiz, concerts, social events
- Static data location: `GOOGLE_CALENDAR_EVENTS` list in `erhardt.py`
- **Limitation**: Static events need manual updates when new events are added

**Faust (REDAXO CMS)**
- URL pattern: `/veranstaltungen/november/211125-le-fly.html`
- Date from URL: DDMMYY format (211125 = 21.11.25)
- Multi-category fetching:
  - rub=2 (Livemusik): All events
  - rub=1 (Party): All events
  - rub=4 (Bühne): English language events only
- English detection: Keywords "english", "englisch", "(en)", "in english"
- Event types in metadata: concert, party, theater

**Pavillon (Custom)**
- Link selector: `a[href*="/event/details/"]`
- Skip cancelled: "Entfällt", "Wird Verschoben", "Abgesagt"
- Category filter: Konzert, Festival, Party

**MusikZentrum (JSON-LD)**
- Parse `<script type="application/ld+json">`
- Filter: `@type == "Event"`
- ISO 8601 dates: `2025-11-22T20:00:00+01:00`

### Anti-Bot Measures
- User-Agent: Chrome 123 on macOS
- Timeout: 30 seconds
- Rate limiting: 1 second delay between sources (BS-4)
- `httpx.Client` with `follow_redirects=True`

### Error Handling
- Individual source failures logged, don't crash workflow
- Graceful degradation: continue with other sources
- Empty results handled gracefully

---

## DATA_FLOW

### Event Model

```python
@dataclass(slots=True, kw_only=True)
class Event:
    title: str
    date: datetime
    venue: str
    url: str
    category: Literal["movie", "culture", "radar"]
    metadata: dict[str, str | int | list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # BS-2: Circuit breaker validation
        # - Title: non-empty, max 200 chars
        # - Venue: max 100 chars
        # - URL: max 500 chars, http/https only
```

**Metadata fields (movies):**
- `duration`: int (minutes)
- `rating`: int (FSK rating)
- `year`: int
- `country`: str
- `genres`: list[str]
- `language`: str ("Sprache: Englisch, Untertitel: Deutsch")
- `poster_url`: str
- `trailer_url`: str
- `cast`: list[dict] (role, name)
- `synopsis`: str

**Metadata fields (concerts):**
- `time`: str ("20:00")
- `event_type`: str ("concert", "sport", "show")
- `status`: str ("available", "sold_out")
- `image_url`: str
- `address`: str
- `genre`: str
- `subtitle`: str
- `price`: str

### Categorization Logic
```python
movies_this_week = [e for e in events if e.category == "movie" and e.is_this_week()]
big_events_radar = [e for e in events if e.category != "movie" and e.date > next_week]
```

### Output Structure
```python
{
    "movies_this_week": [Event, ...],  # Sorted by date
    "big_events_radar": [Event, ...],  # Sorted by date
}
```

### Grouping (for CSV/Markdown)
```python
@dataclass
class GroupedMovie:
    title: str
    year: int
    duration_min: int
    rating: int
    country: str
    genres: list[str]
    synopsis: str
    poster_url: str
    trailer_url: str
    cast: list[dict]
    ticket_url: str
    venue: str
    showtimes: list[Showtime]

@dataclass
class Showtime:
    date: str      # "2025-11-22"
    time: str      # "19:30"
    language: str  # "EN UT:DE"
    has_subtitles: bool
```

---

## API_CONTRACTS

### External APIs

**Astor Cinema API**
- GET `https://backend.premiumkino.de/v1/de/hannover/program`
- Headers: `Accept: application/json`, `Referer: https://hannover.premiumkino.de/`
- Response: `{genres: [], movies: [], performances: []}`
- No auth required
- No rate limit documented

**Telegram Bot API**
- POST `https://api.telegram.org/bot{token}/sendMessage`
- Body: `{chat_id, text, parse_mode: "Markdown"}`
- Rate limit: 30 messages/sec (official)
- Max message length: 4096 chars

### Output Formats

**output/events.json** (enhanced)
```json
{
  "meta": {"week": 47, "year": 2025, "generated_at": "...", "total_movie_showtimes": N},
  "movies": {"unique_films": [...], "all_showtimes": [...]},
  "concerts": [...]
}
```

**output/web_events.json** (frontend)
```json
{
  "meta": {"week": 47, "year": 2025, "updatedAt": "Fri 22 Nov 14:30"},
  "movies": [{"day": "FRI", "date": "22.11", "movies": [...]}],
  "concerts": [{"title": "...", "date": "29 Nov", "day": "Sa", ...}]
}
```

**output/weekly_digest.md** - Human-readable markdown

**output/archive/YYYY-WXX.json** - Weekly snapshots

**output/movies.csv, movies_grouped.csv, concerts.csv** - Flat data exports

---

## STATE_MANAGEMENT

No persistent state. Stateless execution.

### Output Files
- Generated fresh each run
- `output/` directory (gitignored)
- `backup/` for Telegram sends
- `archive/` for historical snapshots

### Caching
None. All data fetched fresh each execution.

---

## CONFIGURATION

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Yes (prod) | Telegram bot authentication |
| `TELEGRAM_CHAT_ID` | Yes (prod) | Target chat/channel |
| `LOG_LEVEL` | No | Logging verbosity (default: INFO) |
| `WEB_EVENTS_PATH` | No | Override web JSON path |

### Constants (config.py)

```python
ASTOR_API_URL = "https://backend.premiumkino.de/v1/de/hannover/program"
REQUEST_TIMEOUT_SECONDS = 30.0
SCRAPE_DELAY_SECONDS = 1.0  # BS-4: Rate limiting between sources
SCRAPE_MAX_RETRIES = 2      # BS-4: Retry configuration
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."
TELEGRAM_MESSAGE_MAX_LENGTH = 4096
GERMAN_MONTH_MAP = {"jan": 1, "februar": 2, ...}
```

### Venue Configs (config.py)
```python
CONCERT_VENUES: tuple[VenueConfig, ...] = (
    {"name": "ZAG Arena", "url": "...", "enabled": True, "selectors": {...}},
    ...
)
```

### Logging
- Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- Destinations: stdout + `kinoweek.log`
- Level: INFO default

---

## DEPENDENCIES

### Python (requires-python = ">=3.13")

| Package | Version | Purpose |
|---------|---------|---------|
| httpx | >=0.27.0 | HTTP client |
| python-dotenv | >=1.0.0 | .env file loading |
| ics | >=0.7.2 | iCal parsing (future) |
| beautifulsoup4 | >=4.12.0 | HTML parsing |
| nh3 | >=0.2.0 | HTML sanitization (replaces deprecated bleach) |

**Dev dependencies:**
- pytest >=9.0.1
- pytest-asyncio >=1.3.0
- pytest-mock >=3.15.1
- ruff >=0.8.0
- mypy >=1.13.0

### Web Frontend (Node.js)

| Package | Version | Purpose |
|---------|---------|---------|
| astro | ^4.16.0 | Static site generator |
| @astrojs/tailwind | ^5.1.0 | Tailwind integration |
| tailwindcss | ^3.4.0 | CSS framework |

### System Requirements
- Python 3.13+
- Node.js 18+ (for web)
- No database
- No Redis

---

## CODE_PATTERNS

### Naming Conventions
- Files: snake_case (`bei_chez_heinz.py`)
- Functions: snake_case (`fetch_all_events`)
- Classes: PascalCase (`BaseSource`, `Event`)
- Constants: UPPER_SNAKE (`ASTOR_API_URL`)
- Type aliases: PascalCase (`EventCategory`, `EventMetadata`)

### Type Hints
- Full type hints everywhere
- `from __future__ import annotations`
- `TYPE_CHECKING` guard for circular imports
- `ClassVar` for class attributes
- `Final` for immutable constants

### Error Handling
```python
# Source-level: catch and log, continue with others
try:
    events = source.fetch()
except Exception as exc:
    logger.warning("Source %s failed: %s", name, exc)
    # Continue - graceful degradation

# Module-level: exception chaining
raise ValueError(msg) from exc
```

### HTTP Client Pattern
```python
def create_http_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )

# Usage
with create_http_client() as client:
    response = client.get(url)
    response.raise_for_status()
```

### Source Registration Pattern
```python
@register_source("source_id")
class MySource(BaseSource):
    source_name: ClassVar[str] = "Human Name"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 20

    def fetch(self) -> list[Event]:
        ...
```

### Dataclass Usage
```python
@dataclass(slots=True, kw_only=True)
class Event:
    ...
```
- `slots=True`: Memory efficiency
- `kw_only=True`: Explicit construction

### Testing Pattern
- Location: `tests/test_scraper.py`
- Naming: `test_*.py`, `Test*` classes, `test_*` methods
- Mocking: `@patch` for HTTP clients
- Structure: arrange/act/assert

---

## INTEGRATIONS

### Telegram Bot
- API: `api.telegram.org/bot{token}/sendMessage`
- Auth: Bot token from BotFather
- Parse mode: Markdown
- Error handling: Log and return False

### Web Frontend Data Flow
```
Python scraper
    ↓
output/web_events.json
    ↓
web/src/data/loader.ts (loadEventData())
    ↓
Astro components
```

Fallback: `mock.ts` if no JSON file

---

## SECURITY

### Input Sanitization (BS-1)
- **Backend**: `sanitize.py` uses `nh3` (Rust-based) to strip all HTML from scraped content
- **Frontend**: `sanitize.ts` blocks dangerous URL protocols (`javascript:`, `data:`)
- **Defense-in-depth**: Sanitization applied at both export and render time

### Model Validation (BS-2)
- `Event.__post_init__()` validates all fields on construction
- Circuit breaker: rejects garbage data from corrupted sources
- Limits: title ≤200 chars, venue ≤100 chars, URL ≤500 chars

### Token Security (BS-3)
- Telegram token handled via `base_url` pattern in httpx
- Exceptions won't leak token in error messages

### Rate Limiting (BS-4)
- 1 second delay between scraper sources
- Prevents IP blocks from rapid requests

### Atomic Writes (DI-1)
- JSON exports use `tempfile` + `shutil.move()`
- Prevents corruption if scraper crashes mid-write
- `dir=output_path` ensures same filesystem for true atomicity

### Security Headers (FS-2)
- CSP: `default-src 'self'; script-src 'self' 'unsafe-inline'`
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin
- HSTS enabled

### German Legal Compliance
- Impressum page (§ 5 DDG, § 18 Abs. 2 MStV)
- Datenschutzerklärung (DSGVO)
- No cookies, no tracking (no consent banner needed)

---

## ACCESSIBILITY (WCAG 2.1 AA)

### Implemented Features
- Skip navigation link for keyboard users
- Proper heading hierarchy with IDs
- `aria-pressed` on theme toggle
- Focus-visible styles for keyboard navigation
- Color contrast meets 4.5:1 ratio (light: #767676, dark: #9ca3af)
- `prefers-reduced-motion` support

---

## KNOWN_ISSUES

| Issue | Cause | Workaround |
|-------|-------|------------|
| Some concerts missing dates | Inconsistent venue HTML | Skip events without parseable dates |
| CSP requires `unsafe-inline` | Astro 4.x inline script bundling | Upgrade to Astro 5.9+ for experimental CSP |
| Erhardt shows 0 Wix Events | Wix JS rendering, no server-side data | Uses static Google Calendar data fallback |
| Erhardt static events outdated | Requires manual updates | Update `GOOGLE_CALENDAR_EVENTS` in erhardt.py periodically |
| Béi Chéz Heinz SSL errors | Intermittent SSL handshake issues | Retry or skip; venue-side issue |

---

## RECENT_CHANGES

| Date | Commit | Description |
|------|--------|-------------|
| 2025-11-23 | ad1464f | Phase 3: Security hardening (validation, rate limiting, atomic writes) |
| 2025-11-23 | 3be5323 | Phase 2: Accessibility (WCAG 2.1 AA compliance) |
| 2025-11-23 | 7e3ba73 | Phase 1: Input sanitization, CSP headers, German legal pages |
| 2025-11-23 | 227b21e | Security audit documentation |
| 2025-11-XX | bfe251b | docs cleanup |
| 2025-11-XX | 568c8bf | Add generated web_events.json to gitignore |
| 2025-11-XX | e52f06e | Replace deprecated apple-mobile-web-app-capable meta tag |
| 2025-11-XX | fc8b74c | Add light/dark theme toggle and event details |
| 2025-11-XX | 974a7b4 | cleanup |
| 2025-11-XX | 17f97f7 | npm to bun |
| 2025-11-XX | 6b9067c | Add data connection, animations, and documentation |
| 2025-11-XX | ffb0c87 | Add boringhannover frontend with Nothing-inspired design |
| 2025-11-XX | 23b43bd | Add 3 new live music sources (Tier 1 venues) |
| 2025-11-XX | f782dea | Add Kulturzentrum Faust as live music source |

---

## TODO

- [x] Input sanitization (nh3 for backend, sanitize.ts for frontend)
- [x] Model validation with circuit breaker
- [x] Rate limiting between sources
- [x] Atomic JSON writes
- [x] Security headers (CSP, HSTS, etc.)
- [x] German legal pages (Impressum, Datenschutz)
- [x] WCAG 2.1 AA accessibility
- [ ] Self-host fonts (optional)
- [ ] Dead link monitoring script
- [ ] Add more concert venues (Lux, Cafe Glocksee)
- [ ] Database persistence for historical analysis
- [ ] Web frontend deployment pipeline
- [ ] iCal feed generation (ics package already installed)
- [ ] Upgrade to Astro 5.9+ for CSP without `unsafe-inline`
- [x] **Faust**: Expand to fetch Party + Bühne (English only) categories
- [ ] **Erhardt**: Implement dynamic Google Calendar scraping or API integration
- [ ] **Erhardt**: Document process for updating static calendar events

---

## TROUBLESHOOTING

### Scraper returns empty results

1. Check network: `curl -I <url>`
2. Check selectors changed: inspect page HTML
3. Check source enabled: `source.enabled`
4. Run with debug: `LOG_LEVEL=DEBUG uv run kinoweek --local`

### Telegram message fails

1. Verify env vars: `echo $TELEGRAM_BOT_TOKEN`
2. Test bot: `curl "https://api.telegram.org/bot{token}/getMe"`
3. Check chat ID: ensure bot is member of channel/group
4. Check message length: max 4096 chars

### Web frontend shows mock data

1. Run scraper: `uv run kinoweek --local`
2. Check file exists: `ls output/web_events.json`
3. Copy to web: `cp output/web_events.json web/output/`

### Tests fail

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test
uv run pytest tests/test_scraper.py::TestEventModel -v

# With coverage
uv run pytest --cov=kinoweek tests/
```

### Type checking fails

```bash
uv run mypy src/kinoweek/
```

### Linting issues

```bash
uv run ruff check src/
uv run ruff format src/
```

---

## COMMANDS_REFERENCE

```bash
# Development
uv run kinoweek --local          # Run scraper, save locally
uv run pytest tests/ -v          # Run tests
uv run ruff check src/           # Lint
uv run mypy src/kinoweek/        # Type check

# Web frontend
cd web && npm run dev            # Start dev server
cd web && npm run build          # Build for production

# Production
uv run kinoweek                  # Run and send to Telegram
```

---

## ADDING_NEW_SOURCE

1. Create file: `src/kinoweek/sources/concerts/venue_name.py`
2. Import base: `from kinoweek.sources.base import BaseSource, register_source, create_http_client`
3. Implement:

```python
@register_source("venue_id")
class VenueSource(BaseSource):
    source_name: ClassVar[str] = "Venue Name"
    source_type: ClassVar[str] = "concert"
    max_events: ClassVar[int | None] = 20

    URL: ClassVar[str] = "https://..."

    def fetch(self) -> list[Event]:
        with create_http_client() as client:
            response = client.get(self.URL)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        return self._parse_events(soup)

    def _parse_events(self, soup: BeautifulSoup) -> list[Event]:
        events = []
        for item in soup.select("..."):
            event = Event(
                title=...,
                date=...,
                venue=self.source_name,
                url=...,
                category="radar",
                metadata={...},
            )
            events.append(event)
        return events
```

4. Source auto-registers on import via `discover_sources()`

---

*Last validated: 2025-11-23*
