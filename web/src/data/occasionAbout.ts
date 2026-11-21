import type { OccasionSummary } from './types';

const adventAbout = [
  {
    id: 'hannover-festivals:weihnachtsmarkt-hannover',
    startDate: '2026-11-23',
    endDate: '2026-12-22',
    description: 'Start with the traditional stalls around the Marktkirche, then walk towards the Leine for the historical market. At Ballhofplatz, the Finnish Christmas village serves Finnish specialities and sells crafts around a Lapland-style tent.',
    url: 'https://www.hannover.de/Veranstaltungskalender/Weihnachten/Weihnachtsmarkt-Hannover',
    source: 'Hannover.de',
  },
  {
    id: 'hannover-festivals:magische-lichterwelten-im-zoo',
    startDate: '2026-11-17',
    endDate: '2027-02-02',
    description: 'Follow an evening trail through illuminated animal figures, interactive light installations and music-and-light shows. Last entry is at 21:00 on listed dates.',
    url: 'https://www.zoo-hannover.de/news/eroeffnung-zoolights-magische-lichterwelten-im-zoo',
    source: 'Erlebnis-Zoo Hannover',
  },
  {
    id: 'hannover-festivals:weihnachtsdorf-auf-dem-lindener-berg',
    startDate: '2026-11-20',
    endDate: '2026-12-20',
    description: 'The Lindener Turm beer garden turns into a free weekend market with changing stalls, choir performances and a fire for baking bread on sticks. On selected Saturdays, the Linden volunteer fire brigade runs hands-on activities.',
    url: 'https://www.hannover.de/Veranstaltungskalender/Weihnachten/Weihnachtsdorf-auf-dem-Lindener-Berg',
    source: 'Hannover.de',
  },
];

export function occasionAbout(
  occasion: Pick<OccasionSummary, 'id' | 'startDate' | 'endDate' | 'sourceStatus'>,
) {
  // Stable slugs can come back in later years. The copy describes these editions.
  if (occasion.sourceStatus && occasion.sourceStatus !== 'scheduled') return undefined;
  return adventAbout.find(about =>
    about.id === occasion.id &&
    about.startDate === occasion.startDate &&
    about.endDate === occasion.endDate,
  );
}
