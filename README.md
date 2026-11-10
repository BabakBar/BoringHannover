# BoringHannover

<p align="center">
  <img src="./web/public/BoringHannover.png" alt="Boring Hannover weekly events illustration" width="800" />
</p>

**Proving Hannover isn't THAT boring!**

Hannover gets a bad rap. [90% destroyed in WWII](https://schikimikki.wordpress.com/2018/04/02/hannover-the-most-boring-city-in-germany/), rebuilt with pragmatic post-war architecture, and known mainly for train connections and trade fairs, it's been called "[exceedingly dull](https://www.flyertalk.com/forum/germany/1322413-what-do-we-all-think-about-hannover.html)." Some say [the greatest risk is dying of boredom](https://www.flyertalk.com/forum/germany/1322413-what-do-we-all-think-about-hannover.html).

Yet the Goethe Institut calls it "[probably the most underrated city in the world](https://www.goethe.de/ins/us/en/m/kul/liv/22597458.html)." too much again, but yeah still not that bad!

**BoringHannover** aggregates cinema, concerts, and cultural events from across the city into a clean weekly digest. Because there's always something happening, you just need to know where to look.

## Current Sources

- **Cinema:** Astor Grand (OV) and Apollokino Hannover (OmU-Nachtstudio)
- **Concerts/events:** ZAG Arena, Swiss Life Hall, Capitol, Faust, Pavillon,
  MusikZentrum, Béi Chéz Heinz, Erhardt Café, Glocksee, Punkrock-Konzerte,
  Kulturpalast Linden, Broncos, Weltspiele (Weidendamm), Platzprojekt, LUX,
  SV Arminia, and Stumpf
- **Sports:** Hannover 96 home matches
- **City Occasions:** automatic discovery from Hannover's official festival
  calendar and selected city Christmas listings, looking 30 days ahead, with
  rich Maschseefest programme enrichment

City Occasions include Berlin today through today + 30 days, inclusive. Movies and
Radar keep their 14-day window. The full occasion index groups the month ahead by
next confirmed appointment; the homepage shows up to two eligible occasions and
replaces ended, cancelled, postponed or exhausted cards with remaining candidates.
Selection runs at build time for no-JS readers and refreshes in the browser each
minute and when the page becomes visible. A fresh backend scrape and frontend
publication are needed to add newly discovered occasions to the public site.

The sitemap lists canonical URLs without `lastmod`: export/check timestamps do
not establish significant content changes to individual pages. The export
timestamp still powers freshness validation and the visible update information.

Occasion details keep confirmed weekday openings and excluded dates, qualify
minimum entry prices as “from”, and offer longer schedules through native
disclosures that work without JavaScript. Unknown conditions stay source-labelled.

## Development

**Backend (Python 3.14+, CI on 3.14 and 3.15, 3.14 in production):**
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

1. Create `src/boringhannover/sources/concerts/your_venue.py` (or use the existing `cinema/`, `festivals/` or `sports/` directory)
2. Implement `BaseSource` with a `fetch()` method
3. Register with `@register_source("your_venue")`

Example:

```python
from boringhannover.sources import BaseSource, register_source
from boringhannover.models import Event

@register_source("my_venue")
class MyVenueSource(BaseSource):
    source_name = "My Venue"
    source_type = "concert"

    def fetch(self) -> list[Event]:
        # Scrape, parse API, whatever works
        return [Event(...)]
```

That's it. No central registry, no config changes. See existing sources in `src/boringhannover/sources/` for inspiration.

**Don't code?** Open an issue with the venue name and website, i'll add it.

## Publication

Each scrape records source outcomes separately from event counts. Production preserves the
current publication when occasion discovery is incomplete or both the movie and Radar
inventories would be empty. A refused run writes local diagnostic output and fails before
backup or GitHub sync. Accepted production runs validate the prior manifest and its
referenced programmes at one Git commit, then preserve eligible known occasions omitted
by complete discovery. Invalid or unavailable prior state stops publication; local runs
skip this read. Interrupted programme uploads recover from the nearest coherent ancestor
with the same manifest, without rewinding newer manifest facts. Newly fetched programme
events join their carried occasion rather than appearing twice in Radar and the programme.
Carried facts retain their original checked timestamp. Occasion programmes upload before
the manifest.

Remaining occasion lifecycle work, including ended-page retention, is tracked in
[#26](https://github.com/BabakBar/BoringHannover/issues/26); exact HTTP expiry belongs to
[#31](https://github.com/BabakBar/BoringHannover/issues/31). Deployments require successful
same-revision CI, including data-only changes and manual runs. Scanned images are promoted
only after a second CI/current-master check. Exact digest pinning through the Coolify
rollout remains [#45](https://github.com/BabakBar/BoringHannover/issues/45).

## Philosophy

> "A side project that ships is worth more than a perfect system that never launches."

File-based. No database. Scheduled scrapes. Filters noise. Ships fast!!

---

**Web:** [boringhannover.de](https://www.boringhannover.de)
**License:** MIT
