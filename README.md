# BoringHannover

**Proving Hannover isn't THAT boring!**

Hannover gets a bad rap. [90% destroyed in WWII](https://schikimikki.wordpress.com/2018/04/02/hannover-the-most-boring-city-in-germany/), rebuilt with pragmatic post-war architecture, and known mainly for train connections and trade fairs, it's been called "[exceedingly dull](https://www.flyertalk.com/forum/germany/1322413-what-do-we-all-think-about-hannover.html)." Some say [the greatest risk is dying of boredom](https://www.flyertalk.com/forum/germany/1322413-what-do-we-all-think-about-hannover.html).

Yet the Goethe Institut calls it "[probably the most underrated city in the world](https://www.goethe.de/ins/us/en/m/kul/liv/22597458.html)." too much again, but yeah still not that bad!

**BoringHannover** aggregates cinema, concerts, and cultural events from across the city into a clean weekly digest. Because there's always something happening, you just need to know where to look.

## Current Sources

**Cinema:** Astor Grand (OV films only)
**Concerts/events:** ZAG Arena, Swiss Life Hall, Capitol, Faust, Pavillon, MusikZentrum, Béi Chéz Heinz, Erhardt

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
