import { describe, expect, test } from 'bun:test';
import type { OccasionSummary } from '../data/types';
import { occasionJsonLd } from './occasionJsonLd';

const base: OccasionSummary = {
  id: 'hannover-festivals:tiergartenfest-hannover',
  slug: 'tiergartenfest-hannover',
  name: 'Tiergartenfest Hannover',
  kind: 'festival',
  startDate: '2026-10-10',
  endDate: '2026-10-10',
  location: 'Tiergarten',
  description: 'Traditionelles Fest.',
  imageUrl: null,
  sourceUrl:
    'https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/Tiergartenfest-Hannover',
  status: 'upcoming',
  programmeCount: 0,
  locationCount: 0,
  programmePath: 'occasions/tiergartenfest-hannover.json',
  preview: [],
};
const urls = {
  canonicalUrl: 'https://boringhannover.de/special/tiergartenfest-hannover/',
  officialUrl: base.sourceUrl,
};

describe('occasionJsonLd', () => {
  test('missing source status does not assert a scheduled event', () => {
    const jsonLd = occasionJsonLd(base, urls);

    expect(jsonLd).not.toHaveProperty('eventStatus');
    expect(jsonLd).toMatchObject({
      '@type': 'Event',
      name: 'Tiergartenfest Hannover',
      startDate: '2026-10-10',
      endDate: '2026-10-10',
      url: urls.canonicalUrl,
      sameAs: urls.officialUrl,
    });
  });

  test('explicit source statuses map to schema.org event statuses', () => {
    expect(occasionJsonLd({ ...base, sourceStatus: 'scheduled' }, urls))
      .toHaveProperty('eventStatus', 'https://schema.org/EventScheduled');
    expect(occasionJsonLd({ ...base, sourceStatus: 'cancelled' }, urls))
      .toHaveProperty('eventStatus', 'https://schema.org/EventCancelled');
    expect(occasionJsonLd({ ...base, sourceStatus: 'postponed' }, urls))
      .toHaveProperty('eventStatus', 'https://schema.org/EventPostponed');
  });

  test('a dated rescheduling keeps the original start date', () => {
    const jsonLd = occasionJsonLd(
      {
        ...base,
        startDate: '2026-10-22',
        endDate: '2026-10-22',
        sourceStatus: 'rescheduled',
        previousStartDate: '2026-10-15',
      },
      urls,
    );

    expect(jsonLd).toMatchObject({
      eventStatus: 'https://schema.org/EventRescheduled',
      startDate: '2026-10-22',
      previousStartDate: '2026-10-15',
    });
  });

  test('dates never carry hours, even when occurrences have them', () => {
    const jsonLd = occasionJsonLd(
      {
        ...base,
        startDate: '2026-10-09',
        endDate: '2026-11-07',
        scheduleConfidence: 'discrete',
        occurrences: [{ date: '2026-10-09', startTime: '18:00' }],
      },
      urls,
    );

    expect(jsonLd.startDate).toBe('2026-10-09');
    expect(jsonLd.endDate).toBe('2026-11-07');
    expect(JSON.stringify(jsonLd)).not.toContain('18:00');
  });
});
