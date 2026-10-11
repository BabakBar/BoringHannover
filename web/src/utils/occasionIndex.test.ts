import { describe, expect, test } from 'bun:test';
import type { OccasionSummary } from '../data/types';
import { indexDates, occasionIndex } from './occasionIndex';

const occasion = (
  slug: string,
  extra: Partial<OccasionSummary> = {},
): OccasionSummary => ({
  id: `hannover-festivals:${slug}`,
  slug,
  name: slug,
  kind: 'festival',
  startDate: '2026-10-11',
  endDate: '2026-10-11',
  location: 'Hannover',
  description: `${slug}. See the source for details.`,
  sourceUrl: `https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/${slug}`,
  status: 'upcoming',
  programmeCount: 0,
  locationCount: 0,
  programmePath: `occasions/${slug}.json`,
  preview: [],
  ...extra,
});
const on = (date: string, extra: Partial<OccasionSummary> = {}) => ({
  startDate: date,
  endDate: date,
  ...extra,
});

// Sun 11 Oct 2026, 12:00 in Berlin. Day 14 is Sun 25 Oct, when clocks go back.
const noon = new Date('2026-10-11T12:00:00+02:00');

const groupOf = (
  items: OccasionSummary[],
  now: Date,
): Record<string, [string, string | null] | undefined> =>
  Object.fromEntries(
    occasionIndex(items, now).flatMap((group) =>
      group.entries.map((entry) => [
        entry.occasion.slug,
        [group.key, entry.appointment?.date ?? null],
      ]),
    ),
  );

describe('occasionIndex', () => {
  test('each occasion lands once, by its next confirmed appointment', () => {
    const cases: Array<[OccasionSummary, [string, string | null] | undefined]> = [
      [occasion('today-untimed', on('2026-10-11')), ['today', '2026-10-11']],
      [occasion('day-7', on('2026-10-18')), ['next', '2026-10-18']],
      [occasion('day-8', on('2026-10-19')), ['following', '2026-10-19']],
      [
        occasion('late-on-day-14', {
          ...on('2026-10-25'),
          scheduleConfidence: 'continuous',
          occurrences: [{ date: '2026-10-25', startTime: '23:30' }],
        }),
        ['following', '2026-10-25'],
      ],
      // Outside the two-week horizon; no discovery surface lists it.
      [occasion('day-15', on('2026-10-26')), undefined],
      [occasion('ended-yesterday', on('2026-10-10')), undefined],
      [
        occasion('running-with-hours-today', {
          startDate: '2026-10-08',
          endDate: '2026-10-11',
          scheduleConfidence: 'continuous',
          occurrences: [{ date: '2026-10-11', startTime: '14:00' }],
        }),
        ['today', '2026-10-11'],
      ],
      // Today's listed hours are over; every envelope date is confirmed.
      [
        occasion('closed-for-today', {
          startDate: '2026-10-10',
          endDate: '2026-10-13',
          scheduleConfidence: 'continuous',
          occurrences: [{ date: '2026-10-11', startTime: '09:00', endTime: '11:00' }],
        }),
        ['next', '2026-10-12'],
      ],
      [
        occasion('closed-for-good', {
          ...on('2026-10-11'),
          scheduleConfidence: 'continuous',
          occurrences: [{ date: '2026-10-11', startTime: '09:00', endTime: '11:00' }],
        }),
        undefined,
      ],
      // The envelope covers today, but only the listed dates are confirmed.
      [
        occasion('sparse', {
          startDate: '2026-10-09',
          endDate: '2026-11-07',
          scheduleConfidence: 'discrete',
          occurrences: [
            { date: '2026-10-09', startTime: '18:00' },
            { date: '2026-10-16', startTime: '18:00' },
            { date: '2026-10-23', startTime: '18:00' },
          ],
        }),
        ['next', '2026-10-16'],
      ],
      // Listed dates are past and later ones were cut at the export horizon.
      [
        occasion('sparse-exhausted', {
          startDate: '2026-10-01',
          endDate: '2026-11-07',
          scheduleConfidence: 'discrete',
          occurrences: [{ date: '2026-10-02', startTime: '18:00' }],
        }),
        ['check', null],
      ],
      // An unparsed or legacy schedule confirms only that it starts on its start date.
      [
        occasion('unknown-ahead', {
          ...on('2026-10-20'),
          endDate: '2026-10-22',
          scheduleConfidence: 'unknown',
        }),
        ['following', '2026-10-20'],
      ],
      [
        occasion('unknown-under-way', {
          startDate: '2026-10-04',
          endDate: '2026-10-18',
          scheduleConfidence: 'unknown',
        }),
        ['check', null],
      ],
      [occasion('legacy-ahead', on('2026-10-14')), ['next', '2026-10-14']],
      [
        occasion('legacy-under-way', { startDate: '2026-10-09', endDate: '2026-10-12' }),
        ['check', null],
      ],
      [occasion('cancelled', on('2026-10-14', { sourceStatus: 'cancelled' })), ['off', null]],
      [occasion('postponed', on('2026-10-14', { sourceStatus: 'postponed' })), ['off', null]],
      [occasion('cancelled-and-over', on('2026-10-10', { sourceStatus: 'cancelled' })), undefined],
      // Rescheduled occasions carry their confirmed new dates.
      [
        occasion('rescheduled', on('2026-10-21', {
          sourceStatus: 'rescheduled',
          previousStartDate: '2026-10-13',
        })),
        ['following', '2026-10-21'],
      ],
    ];

    const result = groupOf(cases.map(([item]) => item), noon);
    for (const [item, expected] of cases) {
      expect(result[item.slug], item.slug).toEqual(expected);
    }
    expect(Object.keys(result)).toHaveLength(
      cases.filter(([, expected]) => expected).length,
    );
  });

  test('groups are fixed, disjoint and dated from the Berlin day', () => {
    const groups = occasionIndex([], noon);
    expect(groups.map(({ key, name, dates }) => [key, name, dates])).toEqual([
      ['today', 'Today', 'Sun 11 Oct'],
      ['next', 'Next 7 days', 'Mon 12 – Sun 18 Oct'],
      ['following', 'Following 7 days', 'Mon 19 – Sun 25 Oct'],
      ['check', 'Check dates', null],
      ['off', 'Cancelled or postponed', null],
    ]);
    expect(groups.every((group) => group.entries.length === 0)).toBe(true);

    // Year rollover: Mon 28 Dec.
    const december = occasionIndex(
      [
        occasion('new-year-day-7', on('2027-01-04')),
        occasion('new-year-day-8', on('2027-01-05')),
      ],
      new Date('2026-12-28T10:00:00+01:00'),
    );
    expect(december.map((group) => group.dates).slice(0, 3)).toEqual([
      'Mon 28 Dec',
      'Tue 29 Dec 2026 – Mon 4 Jan 2027',
      'Tue 5 – Mon 11 Jan',
    ]);
    expect(december[1].entries.map((entry) => entry.occasion.slug)).toEqual([
      'new-year-day-7',
    ]);
    expect(december[2].entries.map((entry) => entry.occasion.slug)).toEqual([
      'new-year-day-8',
    ]);

    // Berlin midnight decides the day, also on the night clocks go back.
    const items = [occasion('sunday', on('2026-10-25'))];
    expect(groupOf(items, new Date('2026-10-24T23:59:00+02:00'))).toEqual({
      sunday: ['next', '2026-10-25'],
    });
    expect(groupOf(items, new Date('2026-10-24T22:00:00Z'))).toEqual({
      sunday: ['today', '2026-10-25'],
    });
    // Spring forward: Sun 29 Mar 2026 is a 23-hour day.
    expect(
      groupOf(
        [occasion('easter-fire', on('2026-04-12'))],
        new Date('2026-03-29T23:30:00+02:00'),
      ),
    ).toEqual({ 'easter-fire': ['following', '2026-04-12'] });
  });

  test('within a group: date, then start time (untimed last), then name', () => {
    const timed = (slug: string, startTime: string) =>
      occasion(slug, {
        ...on('2026-10-11'),
        scheduleConfidence: 'continuous',
        occurrences: [{ date: '2026-10-11', startTime }],
      });
    const groups = occasionIndex(
      [
        occasion('b-untimed'),
        timed('evening', '19:00'),
        occasion('a-untimed'),
        timed('afternoon', '13:00'),
        occasion('later-this-week', on('2026-10-13')),
        occasion('tomorrow', on('2026-10-12')),
        occasion('check-b', { startDate: '2026-10-05', endDate: '2026-10-20' }),
        occasion('check-a', { startDate: '2026-10-05', endDate: '2026-10-20' }),
        occasion('check-earlier', { startDate: '2026-10-01', endDate: '2026-10-20' }),
      ],
      noon,
    );
    const slugs = Object.fromEntries(
      groups.map((group) => [
        group.key,
        group.entries.map((entry) => entry.occasion.slug),
      ]),
    );
    expect(slugs).toEqual({
      today: ['afternoon', 'evening', 'a-untimed', 'b-untimed'],
      next: ['tomorrow', 'later-this-week'],
      following: [],
      check: ['check-earlier', 'check-a', 'check-b'],
      off: [],
    });
  });
});

describe('indexDates', () => {
  test('the grouping appointment first, then the whole run', () => {
    const [sparse, single, running] = [
      occasion('sparse', {
        startDate: '2026-10-09',
        endDate: '2026-11-07',
        scheduleConfidence: 'discrete',
        occurrences: [{ date: '2026-10-16', startTime: '18:00' }],
      }),
      occasion('single', {
        ...on('2026-10-18'),
        scheduleConfidence: 'continuous',
        occurrences: [{ date: '2026-10-18', startTime: '11:00', endTime: '17:00' }],
      }),
      occasion('running', { startDate: '2026-10-08', endDate: '2026-10-12', scheduleConfidence: 'continuous' }),
    ];
    const entries = new Map(
      occasionIndex([sparse, single, running], noon).flatMap((group) =>
        group.entries.map((entry) => [entry.occasion.slug, entry]),
      ),
    );

    expect(indexDates(entries.get('sparse')!)).toEqual({
      when: 'Fri 16 Oct · from 18:00',
      span: 'Selected dates · Fri 9 Oct – Sat 7 Nov',
    });
    expect(indexDates(entries.get('single')!)).toEqual({
      when: 'Sun 18 Oct · 11:00–17:00',
      span: null,
    });
    expect(indexDates(entries.get('running')!)).toEqual({
      when: 'Sun 11 Oct',
      span: 'Thu 8 – Mon 12 Oct',
    });
    // Without a confirmed appointment only the source's dates are shown.
    expect(
      indexDates({
        occasion: { ...sparse, occurrences: [] },
        appointment: null,
      }),
    ).toEqual({
      when: 'Selected dates · Fri 9 Oct – Sat 7 Nov',
      span: null,
    });
  });
});
