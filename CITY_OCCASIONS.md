# City Occasions

Date: 2026-07-26
Status: Implemented on `feat/community-issues`; pre-merge verification in progress

## Decision

BoringHannover will treat festivals and other exceptional city programmes as
**City Occasions**, a first-class product layer beside the calm weekly feed.

An occasion is not an event category or music genre. It is a time-bounded parent
experience—such as Maschseefest, Fête de la Musique, ZINNOBER, a museum night, or
a large neighbourhood celebration—that can contain many programme items.

The product promise remains:

> A calm, trustworthy two-week guide to Hannover, with a beautiful doorway into
> the moments when the whole city is doing something special.

More coverage must not make the homepage feel like a database.

## Why this layer exists

The first Maschseefest integration produced 215 programme items inside a set of
278 events. The existing disclosure encountered a 17-item first day, moved that
day into overflow, and ultimately reduced the experience to one `+278 MORE`
control.

This is an information-architecture problem:

- The weekly feed answers: **What is worth doing soon?**
- A City Occasion answers: **What is happening inside this special moment?**

The two surfaces may share event primitives, but they must not share the same
presentation.

## Implementation status

Stages 1–3 are implemented on `feat/community-issues`:

- registered sources may provide a static occasion definition, discover occasions
  dynamically, or enrich an occasion with programme items;
- the official Hannover `Feste & Festivals` calendar discovers candidate
  occasions without a frontend allowlist;
- matching discoveries are deduplicated against richer programme sources;
- occasion programmes are removed from the ordinary Radar timeline;
- the main manifest contains compact summaries while each complete programme is
  written to `occasions/<slug>.json`;
- the homepage renders one lead occasion and at most two supporting summaries;
- `/special/` keeps every current occasion reachable, while
  `/special/<slug>/` provides the dedicated programme or summary-only state;
- Telegram output summarizes occasions instead of sending hundreds of child
  programme items.

A live local run on 2026-07-26 produced 61 regular Radar events and four active
City Occasions: a 215-item Maschseefest programme, a two-item Fährmannsfest
programme assembled from matching event sources, and two useful summary-only
official listings. Merge and production verification remain.

## Product principles

1. **Calm before comprehensive.** The homepage stays fast to scan.
2. **Occasions are parents, not categories.** Maschseefest is not a genre beside
   Rock, Jazz, Sport, or Party.
3. **Reveal depth by intent.** Full programmes appear only after a user chooses to
   explore an occasion.
4. **Automate coverage, preserve judgment.** Discovery and ingestion are
   automatic; qualification follows explicit rules.
5. **First-party truth wins.** Prefer organiser or city sources, retain
   provenance, and never invent missing times or categories.
6. **Keep the BoringHannover taste.** Typography, space, restrained colour, and
   quiet motion should carry the experience. This must not become a generic card
   carousel or dashboard.

## Experience

### Calm homepage

When an active or upcoming occasion exists, the homepage adds one compact
**Special in Hannover** block alongside the existing Movies and Events on the
Radar surfaces.

An occasion summary may show:

- name, date range, and broad location;
- one short source-owned description;
- `Upcoming`, `Happening now`, or `Final weekend`;
- useful facts such as programme and location counts;
- up to three objective, near-term previews;
- `Today`, `Tonight`, and `Full programme` actions.

These are product constraints:

- at most three occasion summaries;
- at most three programme previews per occasion;
- no complete occasion programme in the homepage DOM;
- no combined count such as `All 278`;
- regular event disclosure must remain useful at any occasion volume.

The occasion block should feel like a temporary magazine cover within the page:
one precise accent, a date-range motif, and the existing category-chip language.

### Dedicated occasion page

Each occasion receives a stable route:

```text
/special/maschseefest-2026/
```

The page prioritises:

1. `Today`, `Tonight`, and `Weekend`;
2. a horizontal date selector;
3. occasion-specific category chips;
4. location or stage filters when supported;
5. a chronological programme grouped by date;
6. progressive disclosure within large days.

The initial programme view remains bounded to roughly 8–12 entries. Categories
are contextual: a festival might use `Music`, `Party`, `Family`, `Food`, `Shows`,
and `Activities`; an art weekend might use `Exhibition`, `Open studio`, `Talk`,
and `Workshop`. Unknown items remain under `All` and are never guessed into a
category.

### Regular event timeline

Regular genre chips and counts apply only to regular events. An occasion item may
also be a concert, but its canonical presentation remains on the occasion page.
The homepage may show only explicitly bounded previews.

## Data boundary

The existing `Event.category` remains responsible for the current aggregation
contract. City Occasions add a separate parent model rather than expanding the
category enum with event names.

Example summary:

```json
{
  "id": "maschseefest-2026",
  "slug": "maschseefest-2026",
  "name": "Maschseefest",
  "kind": "festival",
  "startDate": "2026-07-22",
  "endDate": "2026-08-09",
  "location": "Maschsee",
  "sourceUrl": "https://...",
  "status": "happening_now",
  "programmeCount": 215,
  "programmePath": "occasions/maschseefest-2026.json"
}
```

Programme items reuse trusted event fields and add:

```json
{
  "occasionId": "maschseefest-2026",
  "programmeCategory": "music",
  "locationId": "maschsee-buehne"
}
```

Public output is split by responsibility:

- `web_events.json` contains small occasion summaries for the homepage;
- `occasions/<slug>.json` contains the complete dedicated programme.

This keeps the current stateless Astro build while preventing large programmes
from inflating the homepage payload and component tree.

## Complete automation

Automation has two independent capabilities. This allows broad coverage without
requiring a bespoke programme scraper for every special event.

### 1. Occasion discovery

Discovery sources inspect maintainable first-party indexes such as official city
festival, culture, sport, and seasonal calendars. They emit stable IDs, dates,
location, official URLs, descriptions, and available media.

A candidate qualifies automatically when it:

- is in Hannover or the explicitly supported Hannover area;
- has a reliable organiser-owned or official source;
- is time-bounded;
- and has at least one occasion signal:
  - a parent programme with multiple child events;
  - multiple dates or locations under one identity;
  - an explicit city-wide or seasonal special-event classification;
  - a large official programme that would overwhelm the regular timeline.

Popularity is not required. Specialist communities deserve coverage even when the
maintainer does not know them personally.

Discovery is valuable by itself. If no structured programme exists, the site
publishes a trustworthy summary linking to the official source.

### 2. Programme enrichment

Programme sources attach child items when an official API, feed, structured HTML,
or maintainable detail-page contract exists. They:

- preserve the occasion ID;
- retain direct links and provenance;
- reuse confirmed/fallback time semantics;
- normalize locations without erasing source wording;
- assign only conservative, source-backed categories;
- deduplicate without merging unrelated events;
- fail independently without removing the parent occasion.

### Automated lifecycle

Every scheduled run performs:

```text
discover → qualify → enrich → normalize → deduplicate → publish → expire
```

- `discover`: collect candidates from registered discovery sources;
- `qualify`: apply explicit occasion rules;
- `enrich`: fetch programme items where supported;
- `normalize`: produce stable summaries, locations, and categories;
- `deduplicate`: reconcile the same occasion found through several indexes;
- `publish`: write homepage summaries and per-occasion programmes;
- `expire`: leave active surfaces after the end date while preserving archives.

No database or manual editorial session is required for the first implementation.
A future event store may retain occasion history, but it is not a dependency.

## Quality rules

- Discovery failure must not break ordinary movies and events.
- Programme failure degrades to the occasion summary and official link.
- Every parser uses captured fixtures.
- Unknown times remain hidden; fallback dates remain explicit.
- Programme counts have expected bounds; sudden changes warn instead of flooding
  output.
- Identity uses source IDs and canonical URLs before title heuristics.
- An item never appears twice on the same surface.
- Homepage rendering budgets receive contract tests.
- Empty, upcoming, active, final-weekend, and expired states are deterministic.

## Delivery stages

### Stage 1: contain Maschseefest

Status: implemented on `feat/community-issues`.

- Separate Maschseefest programme items from the regular timeline.
- Fix the oversized-first-day disclosure failure.
- Add occasion-summary and per-occasion programme exports.
- Add the compact homepage occasion block.

Exit: regular events remain immediately visible, no `+278 MORE` failure exists,
and the complete programme stays out of the homepage DOM.

### Stage 2: beautiful programme surface

Status: implemented on `feat/community-issues`.

- Add `/special/maschseefest-2026/`.
- Add time, date, category, and location controls.
- Preserve the existing visual system and motion restraint.
- Validate mobile, keyboard, reduced-motion, empty-filter, and large-day states.

Exit: a user can find a relevant programme item in seconds.

### Stage 3: generalize automation

Status: implemented on `feat/community-issues`.

- Register occasion discovery sources.
- Add qualification, identity, lifecycle, and split-export contracts.
- Convert Maschseefest into the first programme source.
- Add one summary-only occasion to prove graceful degradation.

Exit: a new occasion can appear without frontend code changes or a dedicated
programme scraper.

### Stage 4: broaden carefully

Status: started with the official Hannover festival calendar; additional
first-party discovery surfaces remain future work.

- Add first-party festival, culture, community, seasonal, and major-sport
  discovery surfaces.
- Add rich programme sources only where contracts are maintainable.
- Measure occasion opens, filter use, outbound clicks, and regular-feed scan
  quality.

Exit: coverage expands without increasing homepage density or weekly manual work.

## Success criteria

- No occasion can collapse the regular timeline into an overflow control.
- Active occasions are discovered and expired automatically.
- Summary-only occasions remain useful.
- Rich occasions are navigable by time, date, category, and location.
- A new occasion source requires no homepage component changes.
- Users continue to experience the site as simple, beautiful, and easy to use.

## Non-goals

- Becoming a comprehensive day calendar.
- Ranking items by invented popularity.
- Manually curating hundreds of programme entries.
- Treating every multi-day venue run as a City Occasion.
- Adding accounts or a database solely for this feature.
- Replacing direct organiser links or source attribution.
