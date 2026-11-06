# Hannover city Christmas occasions

Captured 6 November 2026 from the official city listing:
https://www.hannover.de/Kultur-Freizeit/Freizeit-Sport/Feste-Saisonales/Weihnachten-in-der-Region-Hannover/Weihnachtsm%C3%A4rkte-in-der-Stadt-Hannover

- Server-rendered `.interesting-single.line-view-content` cards and the
  `button.more-items` view API are the same contract as the festival calendar.
  No JSON-LD is supplied; robots.txt has no disallow rules at capture time.
- `listing.html` retains all ten cards and the pagination button; `page2.json`
  is the unmodified final API response with two more cards.
- Each detail capture retains the title, summary and complete `#tickets-section`
  (Termine, Ort and admission), without navigation or unrelated page content.
  Detail URLs are the listing card links, not inferred organiser URLs.
- This editor-selected city list includes the zoo light display and Designachten.
  The broader `/Veranstaltungskalender/Weihnachten` category also contains Sea Life,
  workshops, concerts and regional listings; it is not selected for ingestion.
- Lindener Berg opens on listed weekends, not daily. Hauptbahnhof closes on
  25 December and has shorter hours on 24 December; its full end is 30 December.
  Zoo weekday lists/ranges confirm only their stated days, with 24/31 December
  excluded. Its “ab” tariffs remain minimum prices, not unconditional fixed prices.
  Unrecognized schedule qualifiers still retain source wording instead of guessed days.
- Anderten (12 December) is outside the 30-day horizon at capture. Pagination must
  still read it; export, rather than a fabricated end date, controls eligibility.
- Keep the shared `hannover-festivals:<slug>` identity so overlapping city
  calendar listings deduplicate without changing existing occasion routes.

Fixtures describe captured facts, not future-year recurrence. Live publication,
deployment and production-host access require separate verification.
