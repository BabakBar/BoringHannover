# Publication replay fixtures

Single-occasion snapshots copied verbatim from three revisions of the 24 November 2026
scrape run (#136). Only `movies` and `concerts` were emptied and other occasions removed;
`meta`, the occasion summary and the programme file are byte-for-byte the published values.

| Directory | Source revision | Occasion | What it shows |
|---|---|---|---|
| `coherent-0ca2e2a` | `0ca2e2a` (final publication) | `weihnachtsmarkt-hannover` | Summary and programme agree; must load. |
| `conflicting-13e414a` | `13e414a` (intermediate) | `weihnachtsmarkt-hannover` | Same identity and dates, different `status` and `occurrences`; must be rejected. |
| `date-mismatch-b96f37e` | `b96f37e` (intermediate) | `winterwald-am-weiekreuzplatz` | `startDate` differs; must be rejected. |

The scrape published 19 data commits one file at a time. Replaying all of them through the
production loader accepted 13 with conflicting summaries, rejected 3 and accepted 3 coherent
ones. These fixtures are the regression suite for the one-commit publisher (#143).
