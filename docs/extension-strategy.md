# KinoWeek Extension Strategy: Hannover Cultural Aggregator

## Current State

KinoWeek is a production-ready scraper focused on Original Version (OV) movies at Astor Grand Cinema Hannover. It extracts ~45-68 OV showtimes weekly from 400+ total showtimes via direct API access, filters out German dubs, and sends curated schedules to Telegram.

## Vision

Extend KinoWeek into a **Hannover Cultural Events Aggregator** that surfaces all local cultural offerings in one unified, organized feed: cinemas, opera houses, concert halls, theaters, and festivals. This transforms KinoWeek from a niche movie tool into the go-to source for Hannover's cultural calendar.

## Scope

### Geographic Scope
- **Hannover only** (city proper)
- Future: Optional regional expansion

### Filtering Strategy
- **Movies**: Keep existing OV filtering (original language priority)
- **Other venues**: No filtering—show all events
  - Rationale: Operas, concerts, and festivals aren't language-dependent; users scan and choose what interests them

### Output Organization
- **Grouped by type** (not chronological):
  - 🎬 **Movies** (OV-filtered)
  - 🎭 **Opera & Theater**
  - 🎵 **Concerts & Live Music**
  - 🎪 **Festivals & Special Events**
- **Within each group**: Chronological sorting

## Architectural Approach

### Plugin-Based Multi-Source System

Refactor from single hardcoded scraper to pluggable architecture:

1. **Source Configuration** (YAML/JSON)
   - Define venue name, website, scraping method, event category
   - No code changes needed to add venues—only config updates

2. **Abstract Scraper Interface**
   - Base class/protocol for all scrapers
   - Each venue gets its own implementation (API scraper, HTML parser, calendar feed, etc.)
   - Scrapers return normalized event data

3. **Data Normalization Layer**
   - All sources converge to common event schema:
     - Title, date, time, venue, category, description, URL
   - Consistent handling of missing data

4. **Source Registry**
   - Dynamically load scrapers based on config
   - Graceful failure if one source is down

5. **Category-Based Organization**
   - Tag each event with category
   - Notifier groups and formats by category

## Venue Categories & Sources to Target

### 🎬 Cinemas
- **Existing**: Astor Grand Cinema (PremiumKino API)
- **New**: Cinemaxx
- **Access pattern**: Check if PremiumKino powers others, or find direct APIs

### 🎭 Opera & Theater
- **Staatsoper Hannover** (state opera)
- **Schauspielhaus** (drama theater)
- **Ballhof Theater**, others
- **Access pattern**: HTML parsing or calendar feeds (iCal, RSS)

### 🎵 Concerts & Live Music
- **Musikhalle am Maschsee** (concert hall)
- **Capitol, Lux, Pumpehuset** (music venues)
- **Venues with website calendars**
- **Access pattern**: HTML parsing or event listing pages
- Spotify API for concerts?

### 🎪 Festivals & Special Events
- **Bürgerfest, Straßenmusikfest, Jazz-fest** (seasonal)
- **Cultural institutions' websites**
- **Access pattern**: HTML, calendar feeds, or manual curation

## Implementation Principles

### Extensibility First
- Adding a venue = add config entry + implement scraper class
- No changes to core logic or output formatting
- Failures isolated per-source

### Flexible Scraping
- Not all venues have APIs; support multiple strategies:
  - REST/GraphQL APIs (like PremiumKino)
  - HTML parsing (BeautifulSoup)
  - Calendar feeds (iCal/RSS)
  - Direct data entry for festivals (if no automation possible)

### Graceful Degradation
- Missing venue data ≠ entire system failure
- Log failures, continue with working sources
- Notify user of degraded coverage if needed

### Minimal Invasiveness
- Keep notification structure similar to current format
- OV filtering stays movies-only (no other filtering)
- Preserve existing Telegram integration

## Data Model Evolution

Enrich event schema over time:
- **Phase 1**: Title, date, time, venue, category
- **Phase 2**: Venue address, description, ticket URL, price
- **Phase 3**: User preferences per category, filtering, subscriptions

## Success Metrics

- Launch with 2–3 new sources besides movies
- Achieve 80%+ uptime across all sources
- Clear, organized Telegram output grouped by category
- Easy to add new venues (< 30 mins per new source)

## Next Steps

1. **Refactor scraper module**: Create abstract `VenueScraperBase` class
2. **Design data schema**: Event model covering all venue types
3. **Build registry system**: Load scrapers from config
4. **Update notifier**: Group output by category
5. **Add first new source**: Start with opera or concert hall as proof-of-concept
