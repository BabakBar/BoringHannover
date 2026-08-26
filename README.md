# BoringHannover

<p align="center">
  <img src="./web/public/BoringHannover.png" alt="Boring Hannover weekly events illustration" width="800" />
</p>

**Proving Hannover isn't THAT boring!**

Hannover gets a bad rap. [90% destroyed in WWII](https://schikimikki.wordpress.com/2018/04/02/hannover-the-most-boring-city-in-germany/), rebuilt with pragmatic post-war architecture, and known mainly for train connections and trade fairs, it's been called "[exceedingly dull](https://www.flyertalk.com/forum/germany/1322413-what-do-we-all-think-about-hannover.html)." Some say [the greatest risk is dying of boredom](https://www.flyertalk.com/forum/germany/1322413-what-do-we-all-think-about-hannover.html).

Yet the Goethe Institut calls it "[probably the most underrated city in the world](https://www.goethe.de/ins/us/en/m/kul/liv/22597458.html)." too much again, but yeah still not that bad!

**BoringHannover** aggregates cinema, concerts, and cultural events from across the city into a clean weekly digest. Because there's always something happening, you just need to know where to look.

The product stays intentionally calm as coverage grows. Large festivals and
city-wide programmes belong to a separate **City Occasions** layer: one restrained
homepage summary, followed by a dedicated programme for people who want the
detail. See [CITY_OCCASIONS.md](CITY_OCCASIONS.md) for the product and automation
contract and current implementation status.

The mixed **Events on the Radar** feed is browsable by broad, conservative
categories such as Live Music, Party, Workshop, Sport, Market, and Film. Music
genres remain visible where a source provides enough evidence. PLATZprojekt
appears frequently because it is a
[community-run experimental space](https://platzprojekt.de/ueber-uns/) hosting
many independent projects—not a single conventional venue.

## Current Sources

- **Cinema:** Astor Grand (OV) and Apollokino Hannover (OmU-Nachtstudio)
- **Concerts/events:** ZAG Arena, Swiss Life Hall, Capitol, Faust, Pavillon,
  MusikZentrum, Béi Chéz Heinz, Erhardt Café, Glocksee, Punkrock-Konzerte,
  Kulturpalast Linden, Broncos, Weltspiele (Weidendamm), Platzprojekt, LUX,
  SV Arminia, and Stumpf
- **Sports:** Hannover 96 home matches
- **City Occasions:** automatic discovery from Hannover's official festival
  calendar, with rich Maschseefest programme enrichment

Timing accuracy policy and current audit status: [TIMING_ACCURACY.md](TIMING_ACCURACY.md)

## Development

Supported runtimes, update cadence and the supply-chain gates are documented in
[MAINTENANCE.md](MAINTENANCE.md).

**Backend (Python 3.13+, 3.14 in production):**
```bash
uv sync
uv run boringhannover --local
```

**Frontend (Bun 1.4, Astro 7, Tailwind 4):**
```bash
cd web
bun install
bun run dev
```

## Contributing

Know a venue, gallery, theater, or club missing? **love your help!**

Add a new source in 3 steps:

1. Create `src/boringhannover/sources/your_venue.py`
2. Implement `BaseSource` with a `fetch()` method
3. Register with `@register_source("your_venue")`

Example:

```python
from boringhannover.sources import BaseSource, register_source

@register_source("my_venue")
class MyVenueSource(BaseSource):
    source_name = "My Venue"
    source_type = "concert"  # or "cinema", "theater", etc.

    def fetch(self) -> list[Event]:
        # Scrape, parse API, whatever works
        return [Event(...)]
```

That's it. No central registry, no config changes. See existing sources in `src/boringhannover/sources/` for inspiration.

**Don't code?** Open an issue with the venue name and website, i'll add it.

## Philosophy

> "A side project that ships is worth more than a perfect system that never launches."

Stateless. No database. Runs weekly. Filters noise. Ships fast!!

---

**Web:** [boringhannover.de](https://www.boringhannover.de)
**License:** MIT
