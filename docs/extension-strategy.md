# KinoWeek Extension Strategy: Hannover Cultural Aggregator

## Current State (Implemented)

KinoWeek is a production-ready aggregator with a **modular plugin-based architecture**. It currently supports:

| Category | Source | Status |
|----------|--------|--------|
| Cinema | Astor Grand Cinema | ✅ Implemented |
| Concert | ZAG Arena | ✅ Implemented |
| Concert | Swiss Life Hall | ✅ Implemented |
| Concert | Capitol Hannover | ✅ Implemented |

The plugin architecture allows adding new sources with **zero code changes** to core modules - just create a new module with the `@register_source` decorator.

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

## Implemented Architecture

### Plugin-Based Multi-Source System ✅

The following architecture has been implemented:

```
src/kinoweek/sources/
├── __init__.py          # Registry & autodiscovery
├── base.py              # BaseSource ABC + @register_source decorator
├── cinema/
│   └── astor.py         # @register_source("astor_hannover")
└── concerts/
    ├── zag_arena.py     # @register_source("zag_arena")
    ├── swiss_life_hall.py  # @register_source("swiss_life_hall")
    └── capitol.py       # @register_source("capitol_hannover")
```

#### 1. Source Configuration (TOML) ✅
- Configuration in `sources.toml`
- Define venue name, URL, selectors, metadata
- Enable/disable sources via config

#### 2. Abstract Source Interface ✅
```python
class BaseSource(ABC):
    source_name: ClassVar[str]   # Human-readable name
    source_type: ClassVar[str]   # "cinema", "concert", "theater"
    enabled: ClassVar[bool] = True

    @abstractmethod
    def fetch(self) -> list[Event]: ...
```

#### 3. Data Normalization Layer ✅
- All sources return unified `Event` dataclass
- Rich metadata support via flexible dict
- Consistent handling of missing data

#### 4. Source Registry ✅
- `@register_source("name")` decorator for automatic registration
- `get_all_sources()`, `get_sources_by_type()`, `get_source()`
- Graceful failure if one source is down

#### 5. Aggregator ✅
- Central orchestration in `aggregator.py`
- Fetches from all enabled sources
- Categorizes by time horizon (this week vs. radar)

## Adding a New Source

With the implemented architecture, adding a new source is simple:

```python
# sources/concerts/new_venue.py
from kinoweek.sources import BaseSource, register_source
from kinoweek.models import Event

@register_source("new_venue")
class NewVenueSource(BaseSource):
    source_name = "New Venue"
    source_type = "concert"

    URL = "https://www.new-venue.de/events/"

    def fetch(self) -> list[Event]:
        # 1. Fetch HTML/JSON from URL
        # 2. Parse events
        # 3. Return list of Event objects
        ...
```

**Time to add a new source: ~15-30 minutes** (depending on website complexity)

## Venue Categories & Sources to Target

### 🎬 Cinemas
| Venue | Status | Access Pattern |
|-------|--------|----------------|
| Astor Grand Cinema | ✅ Implemented | PremiumKino API |
| CinemaxX Hannover | 📋 Planned | HTML scraping |
| UCI Kinowelt | 📋 Planned | API/HTML |

### 🎭 Opera & Theater
| Venue | Status | Access Pattern |
|-------|--------|----------------|
| Staatsoper Hannover | 📋 Planned | HTML/iCal |
| Schauspiel Hannover | 📋 Planned | HTML |
| GOP Varieté | 📋 Planned | HTML |

### 🎵 Concerts & Live Music
| Venue | Status | Access Pattern |
|-------|--------|----------------|
| ZAG Arena | ✅ Implemented | HTML (WPEM) |
| Swiss Life Hall | ✅ Implemented | HTML (HC-Kartenleger) |
| Capitol Hannover | ✅ Implemented | HTML (HC-Kartenleger) |
| Pavillon Hannover | 📋 Planned | HTML |
| Musikzentrum | 📋 Planned | HTML |

### 🎪 Festivals & Special Events
| Venue | Status | Access Pattern |
|-------|--------|----------------|
| Maschseefest | 📋 Planned | Seasonal HTML |
| Fête de la Musique | 📋 Planned | Seasonal |

## Implementation Principles

### Extensibility First ✅
- Adding a venue = create module + use decorator
- No changes to core logic or output formatting
- Failures isolated per-source

### Flexible Scraping ✅
- REST/GraphQL APIs (like PremiumKino)
- HTML parsing (BeautifulSoup)
- Future: Calendar feeds (iCal/RSS)

### Graceful Degradation ✅
- Missing venue data ≠ entire system failure
- Log failures, continue with working sources
- Individual source errors don't crash aggregator

### Minimal Invasiveness ✅
- Notification structure preserved
- OV filtering stays movies-only
- Existing Telegram integration unchanged

## Data Model Evolution

| Phase | Features | Status |
|-------|----------|--------|
| Phase 1 | Title, date, time, venue, category | ✅ Implemented |
| Phase 2 | Address, description, ticket URL, images | ✅ Implemented |
| Phase 3 | User preferences, filtering, subscriptions | 📋 Planned |

## Success Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Sources besides movies | 2-3 | ✅ 3 (ZAG, Swiss Life, Capitol) |
| Uptime across sources | 80%+ | ✅ Monitored via logs |
| Time to add new venue | < 30 mins | ✅ ~15-30 mins |
| Tests passing | 100% | ✅ 26/26 tests |

## Next Steps

1. ~~Refactor scraper module~~ ✅ Done - `sources/` package created
2. ~~Design data schema~~ ✅ Done - `Event` dataclass with rich metadata
3. ~~Build registry system~~ ✅ Done - `@register_source` decorator
4. ~~Update notifier~~ ✅ Done - Works with new architecture
5. **Add more sources**: CinemaxX, Pavillon, GOP Varieté
6. **Async scraping**: Parallel fetching with `asyncio`
7. **Source health dashboard**: Monitor source availability
