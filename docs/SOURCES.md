# KinoWeek Event Sources

## Overview

KinoWeek aggregates events from 9 sources across Hannover:

| Source | Type | Typical Events | Status |
|--------|------|----------------|--------|
| Astor Grand Cinema | Cinema | ~50 OV showtimes | Active |
| Béi Chéz Heinz | Club | ~2-5 events | Active |
| Capitol Hannover | Large venue | ~10 events | Active |
| Erhardt Café | Café | ~7 events | Active (partial) |
| Kulturzentrum Faust | Cultural center | ~12 events | Active (partial) |
| MusikZentrum | Medium venue | ~15 events | Active |
| Pavillon | Cultural center | ~20 events | Active |
| Swiss Life Hall | Large venue | ~10 events | Active |
| ZAG Arena | Arena | ~9 events | Active |

---

## Cinema Sources

### Astor Grand Cinema (`astor_hannover`)

**URL**: `https://backend.premiumkino.de/v1/de/hannover/program`

**Method**: JSON API

**Filters**:
- Original Version (OV) movies only
- German dubs excluded unless they have subtitles
- Shows only next 7 days ("This Week" section)

**Metadata captured**:
- Title, year, duration, rating (FSK)
- Language, subtitles
- Poster URL, trailer URL
- Genres, country
- Synopsis, cast

**Limitations**: None - comprehensive API access

---

## Concert/Event Sources

### Béi Chéz Heinz (`bei_chez_heinz`)

**URL**: `https://www.beichezheinz.de/programm`

**Method**: HTML scraping (custom layout)

**Filters**: `_Konzert_` category only

**Event types**: Punk, indie, metal concerts

**Limitations**: Low event count typical for this venue

---

### Capitol Hannover (`capitol_hannover`)

**URL**: `https://www.capitol-hannover.de/events/`

**Method**: HTML scraping (HC-Kartenleger plugin)

**Selectors**: `a.hc-card-link-wrapper`

**Metadata captured**:
- Title, date, time
- Image URL
- Sold out status

**Limitations**: None significant

---

### Erhardt Café (`erhardt_cafe`)

**URL**: `https://www.erhardt.cafe/events`

**Method**: Hybrid approach

**How it works**:
1. Attempts to extract Wix Events from embedded JSON (usually returns 0 events)
2. Falls back to static Google Calendar data hardcoded in source

**Event types**:
- Schachabend (chess nights)
- Kniffelabend (game nights)
- Tablequiz (pub quiz)
- Karaoke
- Live concerts
- Social events

**Static data location**: `src/kinoweek/sources/concerts/erhardt.py` - `GOOGLE_CALENDAR_EVENTS` list

**IMPORTANT LIMITATIONS**:
- Wix Events widget renders client-side, no server-side data available
- Static Google Calendar events need **manual updates**
- Last updated: 2025-11-23

**How to update Erhardt events**:
1. Visit https://www.erhardt.cafe/events
2. Check the Google Calendar widget for upcoming events
3. Edit `src/kinoweek/sources/concerts/erhardt.py`
4. Update the `GOOGLE_CALENDAR_EVENTS` tuple list:
   ```python
   GOOGLE_CALENDAR_EVENTS = [
       # (year, month, day, hour, minute, title, event_type)
       (2025, 12, 3, 19, 0, "Kniffelabend", "games"),
       ...
   ]
   ```

---

### Kulturzentrum Faust (`faust_hannover`)

**URL**: `https://www.kulturzentrum-faust.de/veranstaltungen.html?rub=2`

**Method**: HTML scraping (REDAXO CMS)

**Date extraction**: From URL pattern (DDMMYY format)

**IMPORTANT LIMITATIONS**:

Currently only fetches **Livemusik category (rub=2)**!

**Available categories at Faust**:
| Category | rub= | Description | Currently Fetched |
|----------|------|-------------|-------------------|
| Party | 1 | Club nights, DJ events | NO |
| Livemusik | 2 | Live concerts | YES |
| Ausstellung | 3 | Exhibitions | NO |
| Bühne | 4 | Theater, comedy, cabaret | NO |
| Markt | 5 | Markets, fairs | NO |
| Gesellschaft | 6 | Social/political events | NO |
| Literatur | 7 | Readings, book events | NO |
| Fest | 8 | Festivals, celebrations | NO |

**Missing events** (as of 2025-11-23):
- ~10 Party events (90er-Party, 80er-Party, Party 2000, etc.)
- ~9 Bühne events (stand-up comedy, theater shows)
- Literature readings, social events

**Potential improvement**:
Modify the Faust scraper to fetch multiple categories or remove the category filter entirely.

---

### MusikZentrum (`musikzentrum`)

**URL**: `https://musikzentrum-hannover.de/veranstaltungen/`

**Method**: JSON-LD extraction

**Selectors**: `<script type="application/ld+json">`

**Metadata captured**:
- Full structured data from The Events Calendar plugin
- Title, date, time, location
- Image URL

**Limitations**: None significant - clean structured data

---

### Pavillon (`pavillon`)

**URL**: `https://pavillon-hannover.de/programm`

**Method**: HTML scraping (custom layout)

**Selectors**: `a[href*="/event/details/"]`

**Filters**:
- Skips cancelled events ("Entfällt", "Wird Verschoben", "Abgesagt")
- Categories: Konzert, Festival, Party

**Metadata captured**:
- Title, date, time
- Genre (e.g., "Konzert", "Festival")
- Address

**Limitations**: None significant

---

### Swiss Life Hall (`swiss_life_hall`)

**URL**: `https://www.swisslife-hall.de/events/`

**Method**: HTML scraping (HC-Kartenleger plugin)

**Selectors**: `a.hc-card-link-wrapper`

**Metadata captured**:
- Title, date, time
- Image URL
- Sold out status

**Limitations**: None significant

---

### ZAG Arena (`zag_arena`)

**URL**: `https://www.zag-arena-hannover.de/veranstaltungen/`

**Method**: HTML scraping (WordPress Event Manager plugin)

**Selectors**: `.wpem-event-layout-wrapper`

**Metadata captured**:
- Title, date, time
- Address

**Max events**: 15

**Limitations**: None significant

---

## Data Flow Summary

```
Source Scrapers
     │
     ▼
aggregator.fetch_all_events()
     │
     ├── movies (category="movie", this week)
     │
     └── concerts (category="radar", beyond 7 days)
     │
     ▼
notifier.notify()
     │
     ├── Telegram message
     │
     └── Output files:
         ├── web_events.json → Web frontend
         ├── events.json → Full data
         ├── movies.csv, concerts.csv
         ├── weekly_digest.md
         └── archive/YYYY-WXX.json
```

---

## Maintenance Tasks

### Weekly
- Run scraper: `uv run kinoweek --local`
- Verify output looks correct

### Monthly
- Check Erhardt Café for new events, update static list
- Monitor Faust for important non-Livemusik events

### As Needed
- Update scraper selectors if venue websites change
- Add new venues as sources

---

## Adding a New Source

See `docs/technical_context.md` section "ADDING_NEW_SOURCE" for implementation guide.

---

*Last updated: 2025-11-23*
