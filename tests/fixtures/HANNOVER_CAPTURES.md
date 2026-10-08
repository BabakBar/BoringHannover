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
  postponement and rescheduling tests use minimized constructed markup.

## Recapture

```sh
curl -sS "https://www.hannover.de/Veranstaltungskalender/M%C3%A4rkte/Faust-Flohmarkt" -o page.html
```

Then keep only the selectors listed above. Dates in these pages change as the
city updates them; update the test expectations with the new capture date.
