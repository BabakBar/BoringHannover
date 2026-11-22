import { describe, expect, test } from 'bun:test';
import type { OccasionOccurrence, OccasionSummary } from '../data/types';
import { occasionIndex, occasionWeeks, relativeDay, type IndexWindow } from './occasionIndex';
import { berlinClock } from './occasionStatus';

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

/** slug → [part, appointment date, first line]. */
const placements = (items: OccasionSummary[], now: Date, window?: IndexWindow) => {
  const { season, days, check, off } = occasionIndex(items, now, window);
  const row = (part: string) => ({ occasion, appointment, when }: (typeof season)[number]) =>
    [occasion.slug, [part, appointment?.date ?? null, when]] as const;
  return Object.fromEntries([
    ...season.map(row('season')),
    ...days.flatMap(({ date, entries }) => entries.map(row(`day:${date}`))),
    ...check.map(row('check')),
    ...off.map(row('off')),
  ]);
};

test('week cards roll over on Monday in Berlin, including the DST weekend', () => {
  const sunday = new Date('2026-10-25T22:59:00Z');
  const monday = new Date('2026-10-25T23:00:00Z');
  const weeks = (now: Date) => occasionWeeks(berlinClock(now).date);
  expect(weeks(sunday).map(({ startDate, endDate }) => [startDate, endDate])).toEqual([
    ['2026-10-19', '2026-10-25'],
    ['2026-10-26', '2026-11-01'],
    ['2026-11-02', '2026-11-08'],
  ]);
  expect(weeks(monday)[0]).toEqual({ ...weeks(sunday)[1], name: 'This week' });
});

describe('occasionIndex, all dates', () => {
  const continuous = (startDate: string, endDate: string, occurrences: OccasionOccurrence[] = [{ date: startDate }]) =>
    ({ startDate, endDate, scheduleConfidence: 'continuous' as const, occurrences });
  test.each([
    { id: 'one-off today, untimed', item: on('2026-10-11'), expected: ['day:2026-10-11', '2026-10-11', ''] },
    { id: 'day 7', item: on('2026-10-18'), expected: ['day:2026-10-18', '2026-10-18', ''] },
    {
      id: 'late on day 14, the DST night',
      item: { ...on('2026-10-25'), scheduleConfidence: 'continuous' as const, occurrences: [{ date: '2026-10-25', startTime: '23:30' }] },
      expected: ['day:2026-10-25', '2026-10-25', 'from 23:30'],
    },
    { id: 'day 30 is inside the horizon', item: on('2026-11-10'), expected: ['day:2026-11-10', '2026-11-10', ''] },
    { id: 'day 31 is beyond it', item: on('2026-11-11'), expected: undefined },
    { id: 'ended yesterday', item: on('2026-10-10'), expected: undefined },
    {
      id: 'six days is dated, under way: today with hours',
      item: continuous('2026-10-08', '2026-10-13', [{ date: '2026-10-11', startTime: '14:00', endTime: '19:00' }]),
      expected: ['day:2026-10-11', '2026-10-11', '14:00–19:00'],
    },
    {
      id: 'dated, closed for today: tomorrow',
      item: continuous('2026-10-10', '2026-10-13', [{ date: '2026-10-11', startTime: '09:00', endTime: '11:00' }]),
      expected: ['day:2026-10-12', '2026-10-12', ''],
    },
    {
      id: 'closed for good',
      item: { ...on('2026-10-11'), scheduleConfidence: 'continuous' as const, occurrences: [{ date: '2026-10-11', startTime: '09:00', endTime: '11:00' }] },
      expected: undefined,
    },
    {
      id: 'seven days is season-long: open today with hours',
      item: continuous('2026-10-05', '2026-10-11', [{ date: '2026-10-11', startTime: '11:00', endTime: '21:00' }]),
      expected: ['season', '2026-10-11', 'Open today 11:00–21:00'],
    },
    {
      id: 'season-long, open today from a start time',
      item: continuous('2026-10-01', '2026-11-01', [{ date: '2026-10-11', startTime: '14:00' }]),
      expected: ['season', '2026-10-11', 'Open today from 14:00'],
    },
    { id: 'season-long, open today without hours', item: continuous('2026-10-01', '2026-11-01'), expected: ['season', '2026-10-11', 'Open today'] },
    {
      id: 'season-long, closed for today',
      item: continuous('2026-10-01', '2026-11-01', [{ date: '2026-10-11', startTime: '09:00', endTime: '11:00' }]),
      expected: ['season', '2026-10-12', 'Next open Mon 12 Oct'],
    },
    { id: 'season-long, starts later', item: continuous('2026-10-23', '2026-12-23'), expected: ['season', '2026-10-23', 'Opens Fri 23 Oct'] },
    {
      id: 'sparse season: its next listed date',
      item: {
        startDate: '2026-10-09', endDate: '2026-11-07', scheduleConfidence: 'discrete' as const,
        occurrences: [{ date: '2026-10-09', startTime: '18:00' }, { date: '2026-10-16', startTime: '18:00' }],
      },
      expected: ['season', '2026-10-16', 'Next open Fri 16 Oct'],
    },
    {
      id: 'sparse, listed dates exhausted',
      item: { startDate: '2026-10-01', endDate: '2026-11-07', scheduleConfidence: 'discrete' as const, occurrences: [{ date: '2026-10-02', startTime: '18:00' }] },
      expected: ['check', null, 'Selected dates · Thu 1 Oct – Sat 7 Nov'],
    },
    // An unparsed schedule confirms only that it starts on its start date.
    { id: 'unknown, ahead', item: { startDate: '2026-10-20', endDate: '2026-10-22', scheduleConfidence: 'unknown' as const }, expected: ['day:2026-10-20', '2026-10-20', ''] },
    { id: 'unknown season, ahead', item: { startDate: '2026-10-20', endDate: '2026-12-22', scheduleConfidence: 'unknown' as const }, expected: ['season', '2026-10-20', 'Opens Tue 20 Oct'] },
    { id: 'unknown, under way', item: { startDate: '2026-10-04', endDate: '2026-10-18', scheduleConfidence: 'unknown' as const }, expected: ['check', null, 'Sun 4 – Sun 18 Oct'] },
    { id: 'legacy, under way', item: { startDate: '2026-10-09', endDate: '2026-10-12' }, expected: ['check', null, 'Fri 9 – Mon 12 Oct'] },
    { id: 'cancelled', item: on('2026-10-14', { sourceStatus: 'cancelled' }), expected: ['off', null, 'Cancelled · Wed 14 Oct'] },
    { id: 'postponed', item: on('2026-10-14', { sourceStatus: 'postponed' }), expected: ['off', null, 'Postponed · Wed 14 Oct'] },
    { id: 'cancelled and over', item: on('2026-10-10', { sourceStatus: 'cancelled' }), expected: undefined },
    {
      id: 'rescheduled carries its new date',
      item: on('2026-10-21', { sourceStatus: 'rescheduled', previousStartDate: '2026-10-13' }),
      expected: ['day:2026-10-21', '2026-10-21', ''],
    },
  ])('$id', ({ item, expected }) => {
    expect(placements([occasion('x', item as Partial<OccasionSummary>)], noon).x).toEqual(expected as never);
  });

  test('Berlin midnight decides the day, also when clocks change', () => {
    const sunday = [occasion('sunday', on('2026-10-25'))];
    expect(placements(sunday, new Date('2026-10-24T23:59:00+02:00')).sunday[0]).toBe('day:2026-10-25');
    expect(placements(sunday, new Date('2026-10-24T22:00:00Z')).sunday[0]).toBe('day:2026-10-25');
    expect(relativeDay('2026-10-25', new Date('2026-10-24T23:59:00+02:00'))).toBe('Tomorrow');
    expect(relativeDay('2026-10-25', new Date('2026-10-24T22:00:00Z'))).toBe('Today');
    // Spring forward: Sun 29 Mar 2026 is a 23-hour day.
    expect(relativeDay('2026-04-12', new Date('2026-03-29T23:30:00+02:00'))).toBe('in 14 days');
  });

  test('each part sorts by date, then start time with untimed last, then name', () => {
    const timed = (slug: string, date: string, startTime?: string, endDate = date) =>
      occasion(slug, { startDate: date, endDate, scheduleConfidence: 'continuous', occurrences: startTime ? [{ date, startTime }] : [] });
    const { season, days, check } = occasionIndex([
      occasion('b-untimed'),
      timed('evening', '2026-10-11', '19:00'),
      occasion('Ä-untimed'),
      timed('afternoon', '2026-10-11', '13:00'),
      occasion('later-this-week', on('2026-10-13')),
      occasion('tomorrow', on('2026-10-12')),
      timed('market-evening', '2026-10-11', '18:00', '2026-12-23'),
      timed('market-untimed', '2026-10-11', undefined, '2026-12-23'),
      timed('market-noon', '2026-10-11', '12:00', '2026-12-23'),
      timed('market-later', '2026-10-15', '10:00', '2026-12-23'),
      occasion('check-b', { startDate: '2026-10-05', endDate: '2026-10-20' }),
      occasion('check-a', { startDate: '2026-10-05', endDate: '2026-10-20' }),
      occasion('check-earlier', { startDate: '2026-10-01', endDate: '2026-10-20' }),
    ], noon);
    const slugs = (entries: Array<{ occasion: OccasionSummary }>) => entries.map(entry => entry.occasion.slug);
    expect(slugs(season)).toEqual(['market-noon', 'market-evening', 'market-untimed', 'market-later']);
    expect(days.map(({ date, entries }) => [date, slugs(entries)])).toEqual([
      ['2026-10-11', ['afternoon', 'evening', 'Ä-untimed', 'b-untimed']],
      ['2026-10-12', ['tomorrow']],
      ['2026-10-13', ['later-this-week']],
    ]);
    expect(slugs(check)).toEqual(['check-earlier', 'check-a', 'check-b']);
  });
});

test('a week shows each occasion once, at its first opening in that week', () => {
  const now = new Date('2026-10-25T12:00:00+01:00');
  const [thisWeek, nextWeek] = occasionWeeks(berlinClock(now).date);
  const items = [
    occasion('after-next-week', on('2026-11-02')),
    occasion('untimed', on('2026-10-26')),
    occasion('sparse', {
      startDate: '2026-10-24', endDate: '2026-11-02', scheduleConfidence: 'discrete',
      occurrences: [{ date: '2026-10-24' }, { date: '2026-10-28', startTime: '14:00' }, { date: '2026-11-01' }],
    }),
    occasion('unknown-starts-today', { startDate: '2026-10-25', endDate: '2026-11-01', scheduleConfidence: 'unknown' }),
    occasion('unknown-ahead', { startDate: '2026-10-27', endDate: '2026-10-29', scheduleConfidence: 'unknown' }),
    occasion('cancelled', on('2026-10-26', { sourceStatus: 'cancelled' })),
    occasion('market', {
      startDate: '2026-10-25', endDate: '2026-11-04', scheduleConfidence: 'continuous',
      occurrences: [{ date: '2026-10-25', endTime: '11:00' }, { date: '2026-10-26', startTime: '14:00', endTime: '20:00' }],
    }),
    occasion('sunday', on('2026-11-01')),
  ];
  // The market's hours are over for today; an unparsed run is confirmed on its start date.
  expect(placements(items, now, thisWeek)).toEqual({
    'unknown-starts-today': ['season', '2026-10-25', 'Open today'],
  });
  expect(placements(items, now, nextWeek)).toEqual({
    market: ['season', '2026-10-26', 'Mon 26 Oct · 14:00–20:00'],
    untimed: ['day:2026-10-26', '2026-10-26', ''],
    'unknown-ahead': ['day:2026-10-27', '2026-10-27', ''],
    sparse: ['season', '2026-10-28', 'Wed 28 Oct · from 14:00'],
    sunday: ['day:2026-11-01', '2026-11-01', ''],
  });
  // Season rows open today keep "Open today" inside a week too.
  const monday = new Date('2026-10-26T12:00:00+01:00');
  expect(placements(items, monday, occasionWeeks(berlinClock(monday).date)[0]).market)
    .toEqual(['season', '2026-10-26', 'Open today 14:00–20:00']);
});
