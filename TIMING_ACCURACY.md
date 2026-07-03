# Timing Accuracy

Last updated: 2026-07-04

## Current Stage

Event timing now has an explicit confidence contract. The scraper may still use
fallback datetimes internally for sorting date-only listings, but fallback times
must not be displayed as real start times in Telegram, Markdown, CSV, or the web
JSON feed.

The current live audit produced 19 concert events:

- 16 events have confirmed display times from source data.
- 3 events have date-only upstream data and intentionally show no time.
- 0 events expose midnight or default placeholder times as real start times.

## Accuracy Policy

Only show a start time when the source confirms it.

Fallback times are allowed only as internal sort anchors. They are marked with
`metadata["time_confidence"] = "fallback"` and must be hidden from user-facing
outputs.

Confirmed times are marked with `metadata["time_confidence"] = "confirmed"`.
If old source code provides `metadata["time"]` without a confidence flag, it is
treated as confirmed for backward compatibility.

## Output Contract

- Telegram and Markdown: omit fallback times, or use `TBA` where a table cell
  needs an explicit value.
- Web JSON: `time` is `null` for fallback times and `timeConfidence` is
  `"fallback"`.
- Enhanced JSON: `time` is `null` for fallback times and `time_confidence` is
  `"fallback"`.
- CSV: `time` is blank for fallback times and `time_confidence` carries the
  confidence flag.

## Source Progress

- Faust: parses `Einlass / Beginn` including hour-only values like `14 Uhr` and
  split label/value text. The Biergarten Gretchen location no longer causes the
  event title to be truncated.
- Glocksee: reads `Beginn` from Prismic `info_list` and ignores midnight API
  placeholders unless a confirmed time is present.
- Punkrock-Konzerte: keeps date-only listings unknown. Known Kulturpalast event
  URLs are enriched from first-party JSON-LD `startDate` when available.
- Kulturpalast Linden: ICS date-times are confirmed; all-day/date-only entries
  are fallback.
- Capitol, Swiss Life Hall, ZAG Arena, Pavillon, Bei Chez Heinz, MusikZentrum,
  Erhardt, Broncos, and Weltspiele now mark default or date-only anchors as
  fallback instead of exposing them as real times.

## Current Unknown Times

The latest audit still has three events without confirmed start times because
the upstream Punkrock-Konzerte rows are date-only and the linked pages do not
provide a first-party structured event time:

- Shellycoat + Friends with Boats, 2026-07-05, Stumpf
- Rancoeur + Christmas, 2026-07-10, Goldgrube
- Shellycoat + Friends with Boats, 2026-07-11, Garage

These should stay time-unknown until a venue page, ticket page, or structured
data source confirms a start time.

## Next Checks

- Add dedicated source enrichment for recurring Punkrock venues if their own
  pages publish reliable start times.
- Keep tests around fallback display behavior whenever a new exporter is added.
- Watch for source APIs that encode date-only events as midnight datetimes.
  Midnight should be treated as suspicious unless the source explicitly confirms
  `00:00` as the event time.
