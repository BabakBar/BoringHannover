import { expect, test } from 'bun:test';
import type { OccasionOccurrence, OccasionSummary } from '../data/types';
import { posterFacts, posterPath } from './poster';

const occasion = (extra: Partial<OccasionSummary> = {}): OccasionSummary => ({
  id: 'hannover-festivals:markt',
  slug: 'markt',
  name: 'Adventsmarkt',
  kind: 'festival',
  startDate: '2026-11-28',
  endDate: '2026-11-28',
  location: 'Fiedelerplatz',
  description: 'See the source for details.',
  sourceUrl: 'https://www.hannover.de/markt',
  status: 'upcoming',
  programmeCount: 0,
  locationCount: 0,
  programmePath: 'occasions/markt.json',
  preview: [],
  ...extra,
});
const daily = (from: number, to: number, hours: (day: number) => [string, string]): OccasionOccurrence[] =>
  Array.from({ length: to - from + 1 }, (_, index) => {
    const [startTime, endTime] = hours(from + index);
    return { date: `2026-11-${from + index}`, startTime, endTime };
  });

test.each([
  {
    id: 'one day with hours',
    extra: { scheduleConfidence: 'continuous' as const, occurrences: [{ date: '2026-11-28', startTime: '14:00', endTime: '18:00' }] },
    expected: { kicker: 'CITY OCCASION · HANNOVER', date: '28.11', year: '2026', info: 'SAT 14:00–18:00 · FIEDELERPLATZ' },
  },
  {
    id: 'one day from a start time',
    extra: { scheduleConfidence: 'continuous' as const, occurrences: [{ date: '2026-11-28', startTime: '15:00' }] },
    expected: { kicker: 'CITY OCCASION · HANNOVER', date: '28.11', year: '2026', info: 'SAT FROM 15:00 · FIEDELERPLATZ' },
  },
  {
    id: 'one day, unknown hours: the weekday only',
    extra: { scheduleConfidence: 'unknown' as const },
    expected: { kicker: 'CITY OCCASION · HANNOVER', date: '28.11', year: '2026', info: 'SAT · FIEDELERPLATZ' },
  },
  {
    id: 'every day with the same hours',
    extra: { startDate: '2026-11-23', endDate: '2026-11-29', scheduleConfidence: 'continuous' as const, occurrences: daily(23, 29, () => ['11:00', '21:00']) },
    expected: { kicker: 'CITY OCCASION · HANNOVER', date: '23.11–29.11', year: '2026', info: 'DAILY 11:00–21:00 · FIEDELERPLATZ' },
  },
  {
    id: 'hours that vary: no schedule claim',
    extra: { startDate: '2026-11-23', endDate: '2026-12-22', scheduleConfidence: 'continuous' as const, occurrences: daily(23, 29, day => [day > 27 ? '10:00' : '11:00', '21:00']) },
    expected: { kicker: 'CITY OCCASION · HANNOVER', date: '23.11–22.12', year: '2026', info: 'FIEDELERPLATZ' },
  },
  {
    id: 'listed dates only',
    extra: { startDate: '2026-11-12', endDate: '2027-01-31', scheduleConfidence: 'discrete' as const, occurrences: [{ date: '2026-11-12', startTime: '17:00' }] },
    expected: { kicker: 'CITY OCCASION · HANNOVER', date: '12.11–31.01', year: '2026–2027', info: 'SELECTED DATES · FIEDELERPLATZ' },
  },
  {
    id: 'a weekend: its weekdays',
    extra: { startDate: '2026-11-28', endDate: '2026-11-29' },
    expected: { kicker: 'CITY OCCASION · HANNOVER', date: '28.11–29.11', year: '2026', info: 'SAT–SUN · FIEDELERPLATZ' },
  },
  {
    id: 'a long unparsed run: no weekday range',
    extra: { startDate: '2026-11-23', endDate: '2026-12-22', scheduleConfidence: 'unknown' as const },
    expected: { kicker: 'CITY OCCASION · HANNOVER', date: '23.11–22.12', year: '2026', info: 'FIEDELERPLATZ' },
  },
  {
    id: 'a day trip names its town',
    extra: { area: 'region' as const, place: { venue: 'Hof', street: 'Lange Straße 1', postalCode: '31832', locality: 'Eldagsen', municipality: 'Springe' } },
    expected: { kicker: 'DAY TRIP · SPRINGE', date: '28.11', year: '2026', info: 'SAT · HOF' },
  },
  {
    id: 'cancelled says so first',
    extra: { sourceStatus: 'cancelled' as const },
    expected: { kicker: 'CANCELLED · CITY OCCASION · HANNOVER', date: '28.11', year: '2026', info: 'SAT · FIEDELERPLATZ' },
  },
  {
    id: 'postponed says so first',
    extra: { sourceStatus: 'postponed' as const },
    expected: { kicker: 'POSTPONED · CITY OCCASION · HANNOVER', date: '28.11', year: '2026', info: 'SAT · FIEDELERPLATZ' },
  },
])('posterFacts: $id', ({ extra, expected }) => {
  expect(posterFacts(occasion(extra as Partial<OccasionSummary>))).toEqual(expected);
});

test('a changed fact gets a new poster URL, an unchanged one keeps it', () => {
  const path = posterPath(occasion());
  expect(path).toMatch(/^\/occasion-posters\/markt-[0-9a-f]{8}\.png$/);
  expect(posterPath(occasion())).toBe(path);
  expect(posterPath(occasion({ description: 'Other prose' }))).toBe(path);
  expect(posterPath(occasion({ sourceStatus: 'cancelled' }))).not.toBe(path);
  expect(posterPath(occasion({ startDate: '2026-11-29', endDate: '2026-11-29' }))).not.toBe(path);
});
