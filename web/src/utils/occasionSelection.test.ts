import { describe, expect, test } from 'bun:test';
import type { OccasionOccurrence, OccasionSummary } from '../data/types';
import { boardSelection } from './occasionSelection';

const occasion = (slug: string, extra: Partial<OccasionSummary> = {}): OccasionSummary => ({
  id: `hannover-festivals:${slug}`,
  slug,
  name: slug,
  kind: 'festival',
  startDate: '2026-11-22',
  endDate: '2026-11-22',
  location: 'Hannover',
  description: `${slug}. See the source for details.`,
  sourceUrl: `https://www.hannover.de/${slug}`,
  status: 'upcoming',
  programmeCount: 0,
  locationCount: 0,
  programmePath: `occasions/${slug}.json`,
  preview: [],
  ...extra,
});
const timed = (date: string, startTime?: string, endTime?: string, extra: Partial<OccasionSummary> = {}) => ({
  startDate: date,
  endDate: date,
  scheduleConfidence: 'continuous' as const,
  occurrences: [{ date, startTime, endTime }] as OccasionOccurrence[],
  ...extra,
});

// Sun 22 Nov 2026, 15:00 in Berlin.
const afternoon = new Date('2026-11-22T15:00:00+01:00');

/** slug → [part, when, end, now, opens]. */
const rows = (items: OccasionSummary[], now = afternoon, live = true) => {
  const board = boardSelection(items, now, { live });
  return Object.fromEntries([
    ...board.today.map(row => [row.occasion.slug, ['today', row.when, row.end, row.now, row.opens]]),
    ...board.coming.map(row => [row.occasion.slug, ['coming', row.when, row.end, row.now, row.opens]]),
  ]);
};

describe('boardSelection rows', () => {
  test.each([
    { id: 'inside a confirmed interval: On now', item: timed('2026-11-22', '14:00', '20:00'), expected: ['today', 'On now', '–20:00', true, false] },
    { id: 'start-only and begun: From, never On now', item: timed('2026-11-22', '14:00'), expected: ['today', 'From 14:00', null, false, false] },
    { id: 'later today: the start time', item: timed('2026-11-22', '17:00', '22:00'), expected: ['today', '17:00', '–22:00', false, false] },
    { id: 'untimed today', item: { startDate: '2026-11-22', endDate: '2026-11-22' }, expected: ['today', 'Today', null, false, false] },
    { id: 'closed for today, single day: gone', item: timed('2026-11-22', '10:00', '12:00'), expected: undefined },
    { id: 'unparsed run starting today', item: { startDate: '2026-11-22', endDate: '2026-11-29', scheduleConfidence: 'unknown' as const }, expected: ['today', 'Today', null, false, false] },
    { id: 'unparsed run under way: nothing confirmed', item: { startDate: '2026-11-20', endDate: '2026-11-29', scheduleConfidence: 'unknown' as const }, expected: undefined },
    { id: 'tomorrow', item: timed('2026-11-23', '16:00', '20:00'), expected: ['coming', 'Mon 23', '16:00', false, false] },
    { id: 'day 7 is coming up', item: { startDate: '2026-11-29', endDate: '2026-11-29' }, expected: ['coming', 'Sun 29', null, false, false] },
    { id: 'day 8 is not', item: { startDate: '2026-11-30', endDate: '2026-11-30' }, expected: undefined },
    { id: 'a season opening this week', item: timed('2026-11-23', '11:00', '21:00', { endDate: '2026-12-23' }), expected: ['coming', 'Mon 23', '11:00', false, true] },
    {
      id: 'a running season closed for today waits, not coming up',
      item: { startDate: '2026-11-01', endDate: '2026-12-23', scheduleConfidence: 'continuous' as const, occurrences: [{ date: '2026-11-22', startTime: '10:00', endTime: '12:00' }] },
      expected: undefined,
    },
    { id: 'cancelled', item: timed('2026-11-22', '14:00', '20:00', { sourceStatus: 'cancelled' }), expected: undefined },
    { id: 'postponed', item: { startDate: '2026-11-23', endDate: '2026-11-23', sourceStatus: 'postponed' as const }, expected: undefined },
    { id: 'rescheduled keeps its new date', item: { startDate: '2026-11-23', endDate: '2026-11-23', sourceStatus: 'rescheduled' as const }, expected: ['coming', 'Mon 23', null, false, false] },
  ])('$id', ({ item, expected }) => {
    expect(rows([occasion('x', item as Partial<OccasionSummary>)]).x).toEqual(expected as never);
  });

  test('the build has no time-of-day labels, which a static page cannot keep true', () => {
    expect(rows([
      occasion('on', timed('2026-11-22', '14:00', '20:00')),
      occasion('from', timed('2026-11-22', '14:00')),
      occasion('untimed'),
      occasion('tomorrow', timed('2026-11-23', '16:00')),
    ], afternoon, false)).toEqual({
      on: ['today', '14:00', '–20:00', false, false],
      from: ['today', '14:00', null, false, false],
      untimed: ['today', 'Sun 22', null, false, false],
      tomorrow: ['coming', 'Mon 23', '16:00', false, false],
    });
  });
});

test('today: one-offs before season-long, then start time with untimed last, then name; four at most', () => {
  const season = (slug: string, startTime?: string) =>
    occasion(slug, timed('2026-11-22', startTime, undefined, { startDate: '2026-11-01', endDate: '2026-12-23' }));
  const board = boardSelection([
    season('market-noon', '12:00'),
    occasion('b-untimed'),
    occasion('evening', timed('2026-11-22', '18:00')),
    occasion('Ä-untimed'),
    season('market-untimed'),
    occasion('morning', timed('2026-11-22', '09:00', '23:00')),
  ], afternoon);
  expect(board.today.map(row => row.occasion.slug)).toEqual(['morning', 'evening', 'Ä-untimed', 'b-untimed']);
  expect(board.todayMore).toBe(2);
});

test('coming up: by date, then time; three at most; the total matches the index', () => {
  const board = boardSelection([
    occasion('wed', { startDate: '2026-11-25', endDate: '2026-11-25' }),
    occasion('mon-late', timed('2026-11-23', '19:00')),
    occasion('mon-early', timed('2026-11-23', '10:00')),
    occasion('tue', { startDate: '2026-11-24', endDate: '2026-11-24' }),
    occasion('later', { startDate: '2026-12-10', endDate: '2026-12-10' }),
    occasion('beyond', { startDate: '2026-12-31', endDate: '2026-12-31' }),
    occasion('cancelled', { startDate: '2026-11-24', endDate: '2026-11-24', sourceStatus: 'cancelled' }),
    occasion('unknown-under-way', { startDate: '2026-11-20', endDate: '2026-11-29', scheduleConfidence: 'unknown' }),
  ], afternoon);
  expect(board.coming.map(row => row.occasion.slug)).toEqual(['mon-early', 'mon-late', 'tue']);
  // The index's "N occasions in the next 30 days": not cancelled, beyond or undated.
  expect(board.total).toBe(5);
});
