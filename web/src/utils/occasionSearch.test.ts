import { describe, expect, test } from 'bun:test';
import type { OccasionSummary } from '../data/types';
import { isFallbackDescription, searchDescription, searchTitle } from './occasionSearch';

const place = { venue: 'Marktkirche', street: 'Hanns-Lilje-Platz 2', postalCode: '30159', locality: 'Hannover' };
const occasion = (extra: Partial<OccasionSummary>): OccasionSummary => ({
  id: 'search:x', slug: 'x', name: 'Weihnachtsmarkt Altstadt', kind: 'festival',
  startDate: '2026-12-05', endDate: '2026-12-05', location: 'Altstadt',
  description: 'Weihnachtsmarkt Altstadt at Altstadt. See the source for details.',
  sourceUrl: 'https://www.hannover.de/x', status: 'upcoming',
  programmeCount: 0, locationCount: 0, programmePath: 'occasions/x.json', preview: [],
  ...extra,
});
const daily = (from: number, to: number, hours: (day: number) => [string, string]) =>
  Array.from({ length: to - from + 1 }, (_, index) => {
    const day = from + index;
    const [startTime, endTime] = hours(day);
    return { date: `2026-11-${String(day).padStart(2, '0')}`, startTime, endTime };
  });

describe('searchTitle', () => {
  test.each([
    { id: 'one day adds the city', extra: {}, expected: 'Weihnachtsmarkt Altstadt · Sat 5 Dec 2026 · Hannover' },
    { id: 'a range in one year names the year once', extra: { startDate: '2026-11-23', endDate: '2026-12-22' }, expected: 'Weihnachtsmarkt Altstadt · 23 Nov – 22 Dec 2026 · Hannover' },
    { id: 'a cross-year range names both years', extra: { startDate: '2026-11-12', endDate: '2027-01-31' }, expected: 'Weihnachtsmarkt Altstadt · 12 Nov 2026 – 31 Jan 2027 · Hannover' },
    { id: 'a Region occasion names its municipality', extra: { area: 'region' as const, place: { ...place, locality: 'Seelze', municipality: 'Seelze' } }, expected: 'Weihnachtsmarkt Altstadt · Sat 5 Dec 2026 · Seelze' },
    { id: 'a name containing Hannover is not repeated', extra: { name: 'Weihnachtsmarkt Hannover' }, expected: 'Weihnachtsmarkt Hannover · Sat 5 Dec 2026' },
    { id: 'no place when the title would exceed 65 characters', extra: { name: 'Lebendiger Adventskalender in der Südstadt' }, expected: 'Lebendiger Adventskalender in der Südstadt · Sat 5 Dec 2026' },
  ])('$id', ({ extra, expected }) => {
    expect(searchTitle(occasion(extra))).toBe(expected);
  });
});

describe('searchDescription', () => {
  test.each([
    {
      id: 'one timed day',
      extra: { place, scheduleConfidence: 'continuous' as const, occurrences: [{ date: '2026-12-05', startTime: '14:00', endTime: '19:00' }] },
      expected: 'Saturday 5 December 2026, 14:00–19:00 at Marktkirche, Hanns-Lilje-Platz 2, 30159 Hannover.',
    },
    {
      id: 'one untimed day, no venue',
      extra: { place: { ...place, venue: undefined } },
      expected: 'Saturday 5 December 2026 at Hanns-Lilje-Platz 2, 30159 Hannover.',
    },
    {
      id: 'one day with an unknown schedule and no structured address',
      extra: { scheduleConfidence: 'unknown' as const, occurrences: [] },
      expected: 'Saturday 5 December 2026 at Altstadt.',
    },
    {
      id: 'continuous with identical daily hours',
      extra: { startDate: '2026-11-23', endDate: '2026-11-29', scheduleConfidence: 'continuous' as const, occurrences: daily(23, 29, () => ['11:00', '21:00']) },
      expected: 'Daily 11:00–21:00, 23 November – 29 November 2026 at Altstadt.',
    },
    {
      id: 'continuous with varying hours keeps the range',
      extra: { startDate: '2026-11-23', endDate: '2026-11-29', scheduleConfidence: 'continuous' as const, occurrences: daily(23, 29, day => [day > 27 ? '10:00' : '11:00', '21:00']) },
      expected: '23 November – 29 November 2026 at Altstadt.',
    },
    {
      id: 'continuous with confirmed hours on only some days keeps the range',
      extra: { startDate: '2026-11-23', endDate: '2026-11-29', scheduleConfidence: 'continuous' as const, occurrences: daily(23, 25, () => ['11:00', '21:00']) },
      expected: '23 November – 29 November 2026 at Altstadt.',
    },
    {
      id: 'discrete dates',
      extra: { startDate: '2026-11-12', endDate: '2027-01-31', scheduleConfidence: 'discrete' as const, occurrences: [{ date: '2026-11-12', startTime: '17:00' }] },
      expected: 'Selected dates from 12 November 2026 to 31 January 2027 at Altstadt.',
    },
    {
      id: 'unknown schedule across years',
      extra: { startDate: '2026-12-20', endDate: '2027-01-06', scheduleConfidence: 'unknown' as const },
      expected: '20 December 2026 – 6 January 2027 at Altstadt.',
    },
    {
      id: 'one unconditional free row',
      extra: { admission: [{ price: 'free' as const }] },
      expected: 'Saturday 5 December 2026 at Altstadt. Free entry.',
    },
    {
      id: 'conditional prices are not summarised',
      extra: { admission: [{ label: 'Kinder', price: 'free' as const }, { label: 'Erwachsene', price: '€5.00' }] },
      expected: 'Saturday 5 December 2026 at Altstadt.',
    },
    {
      id: 'cancelled is said first',
      extra: { sourceStatus: 'cancelled' as const },
      expected: 'Cancelled: Saturday 5 December 2026 at Altstadt.',
    },
    {
      id: 'a programme keeps its sentence',
      extra: { programmeCount: 12 },
      expected: 'Saturday 5 December 2026 at Altstadt. Explore the official programme by day, category, and location.',
    },
  ])('$id', ({ extra, expected }) => {
    expect(searchDescription(occasion(extra), null)).toBe(expected);
  });

  test('includes real About text', () => {
    expect(searchDescription(occasion({}), 'Stalls around the Marktkirche.')).toBe(
      'Saturday 5 December 2026 at Altstadt. Stalls around the Marktkirche.',
    );
  });
});

test.each([
  { id: 'exporter fallback', text: 'Lister Turm at Lister Turm. See the source for details.', expected: true },
  { id: 'empty', text: '', expected: true },
  { id: 'real text', text: 'A winter village with a skating rink.', expected: false },
])('isFallbackDescription: $id', ({ text, expected }) => {
  expect(isFallbackDescription(text)).toBe(expected);
});
