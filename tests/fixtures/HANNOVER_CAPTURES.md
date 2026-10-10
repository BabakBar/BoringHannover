# hannover.de fixture capture notes

Minimized excerpts of public official pages on `https://www.hannover.de`. Each
fixture keeps only the selectors the parser reads; page chrome, scripts and
tracking markup are removed. Times are UTC.

| Fixture | Source URL | Captured | Kept selectors |
| --- | --- | --- | --- |
| `hannover_market_detail_faust_flohmarkt.html` | `/Veranstaltungskalender/Märkte/Faust-Flohmarkt` | 2026-10-08T22:02:56Z | `.details` |
| `hannover_market_detail_neue_bult.html` | `/Veranstaltungskalender/Märkte/Flohmarkt-auf-der-Neuen-Bult` | 2026-10-08T22:02:56Z | `.details` |
| `hannover_festival_detail_wiesn.html` | `/Veranstaltungskalender/Feste-Festivals/Hannover-Wies%27n` | 2026-10-08T22:02:11Z | `.details` |
| `hannover_festival_detail_oktoberfest.html` | `/Veranstaltungskalender/Feste-Festivals/Oktoberfest-2026` | 2026-10-08T22:02:11Z | `.details` |
| `hannover_festival_detail_winterzauber.html` | `/Veranstaltungskalender/Feste-Festivals/Winterzauber-Herrenhausen` | 2026-10-08T22:02:12Z | `.details` |
| `hannover_concert_detail_cancelled.html` | `/Veranstaltungskalender/Konzerte/Abgesagt-Zum-ersten-Mal-in-Hannover-K-Pop-Forever` | 2026-10-08T22:06:15Z | `h1.content-detail__title`, `.content-detail__summary`, `.details` |
| `hannover_festival_detail_tiergartenfest.html` (recaptured) | `/Veranstaltungskalender/Feste-Festivals/Tiergartenfest-Hannover` | 2026-10-09T23:41:02Z | `.details-table.max-w-90` (Termine, Ort, nested price `.table.details-table`) |
| `hannover_festival_detail_kunst_kurbis.html` | `/Veranstaltungskalender/Feste-Festivals/Kunst-K%C3%BCrbis-in-Eldagsen` | 2026-10-09T23:41:02Z | `.details-table.max-w-90` (Termine, Ort, free-entry sentence) |

The fixtures from #58 (`hannover_festivals_listing.html`, `hannover_festivals_page2.json`,
`hannover_festival_detail_kiezkultur.html`, `hannover_festival_detail_tiergartenfest.html`)
were committed in `6ffbecd` without a recorded capture time.

## What the captures show

- Termine rows put one appointment per `<p>`. A range reads
  `DD.MM.YYYY bis DD.MM.YYYY ab HH:MM [bis HH:MM] Uhr`; a single date drops the
  `bis DD.MM.YYYY` part. Weekday recurrences append text such as `sonntags`.
- Exclusions follow a `<strong>Die Veranstaltung findet nicht statt am:</strong>`
  label, one excluded date per `<p>`.
- The listing start date rolls forward as dates pass: Faust read
  `04.10.2026 bis 18.10.2026` in the #59 report and `11.10.2026 bis 18.10.2026`
  on 8 Oct. That is not a rescheduling.
- A cancelled entry prefixes its title with `Abgesagt: `; Termine keeps the
  original date. Search results on the same day showed the same convention as
  `Verschoben: ` for postponements, but no published postponed page was
  reachable (archived pages return 404, unpublished ones redirect to login), so
  postponement and rescheduling tests use minimized constructed markup. An
  independent review (9 Oct) saw a search-cache rendering, not a capture, of the
  official Nena page using `ursprünglich für … ist auf …`. The parser does not
  read that wording, so such a page stays `postponed` without a previous date.

- The Ort row reads `[venue,] street with house number, PLZ locality`, one line
  per `<br>`. A Region event names its own municipality there (Kunst & Kürbis:
  `31832 Springe`), checked against the official list at
  `/Leben-in-der-Region-Hannover/Verwaltungen-Kommunen/Kommunen-in-der-Region-Hannover`
  (read 2026-10-09T23:43:13Z: Hannover plus 20 towns and municipalities).
- Prices are a nested `.table.details-table` of label/value rows under Termine
  and Ort. Tiergartenfest lists `Mit Baumscheibe (…) frei`, `Erwachsene 3 €`,
  `Kinder (bis 14 Jahre) 2 €`: the free row is a condition, not free entry.
  A free event instead carries the sentence `Dies ist eine Veranstaltung mit
  freiem Eintritt`. Oktoberfest, Wies'n and KiezKultur listed no prices.

## Recapture

Send the source's own User-Agent (`HannoverFestivalCalendarSource.USER_AGENT`),
so captures and scrapes identify themselves the same way:

```sh
curl -sS -A "BoringHannover (+https://boringhannover.de/impressum/; https://github.com/BabakBar/BoringHannover)" \
  "https://www.hannover.de/Veranstaltungskalender/M%C3%A4rkte/Faust-Flohmarkt" -o page.html
```

On 2026-10-10T00:20:01Z a live discovery run with that User-Agent read the
listing, its load-more page and five detail pages, each answering `200 OK`.

Then keep only the selectors listed above. Dates in these pages change as the
city updates them; update the test expectations with the new capture date.
