import { describe, expect, test } from 'bun:test';
import type { OccasionSummary } from '../data/types';
import {
  entryPrice,
  mapUrl,
  onwardOccasions,
  placeAddress,
  sheetDateLine,
  tileAppointment,
  tileFace,
  whenFacts,
} from './occasionSheet';

const base: OccasionSummary = {
  id: 'hannover-festivals:tiergartenfest-hannover',
  slug: 'tiergartenfest-hannover',
  name: 'Tiergartenfest Hannover',
  kind: 'festival',
  startDate: '2026-10-10',
  endDate: '2026-10-10',
  location: 'Tiergarten',
  description: 'Tiergartenfest Hannover at Tiergarten. See the source for details.',
  sourceUrl:
    'https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/Tiergartenfest-Hannover',
  status: 'upcoming',
  programmeCount: 0,
  locationCount: 0,
  programmePath: 'occasions/tiergartenfest-hannover.json',
  preview: [],
};
const occasion = (
  slug: string,
  extra: Partial<OccasionSummary> = {},
): OccasionSummary => ({
  ...base,
  id: `hannover-festivals:${slug}`,
  slug,
  name: slug,
  programmePath: `occasions/${slug}.json`,
  ...extra,
});

describe('sheetDateLine', () => {
  test('one day, one month, and across months', () => {
    expect(sheetDateLine(base)).toBe('Sat 10 Oct');
    expect(sheetDateLine({ ...base, startDate: '2026-10-08', endDate: '2026-10-11' }))
      .toBe('Thu 8 – Sun 11 Oct');
    expect(sheetDateLine({ ...base, startDate: '2026-10-09', endDate: '2026-11-07' }))
      .toBe('Fri 9 Oct – Sat 7 Nov');
    expect(sheetDateLine({ ...base, startDate: '2026-12-31', endDate: '2027-01-01' }))
      .toBe('Thu 31 Dec 2026 – Fri 1 Jan 2027');
  });
});

describe('whenFacts', () => {
  test('a one-day occasion with confirmed hours is one appointment', () => {
    expect(
      whenFacts({
        ...base,
        scheduleConfidence: 'continuous',
        occurrences: [{ date: '2026-10-10', startTime: '13:00', endTime: '18:30' }],
      }),
    ).toEqual({
      range: null,
      appointments: [
        { date: '2026-10-10', datetime: '2026-10-10T13:00', text: 'Sat 10 Oct · 13:00–18:30' },
      ],
      selectedDatesOnly: false,
      sourceHours: null,
    });
  });

  test('a continuous run lists each day it has hours for', () => {
    const facts = whenFacts({
      ...base,
      startDate: '2026-10-08',
      endDate: '2026-10-11',
      scheduleConfidence: 'continuous',
      occurrences: [
        { date: '2026-10-10', startTime: '15:00' },
        { date: '2026-10-11', startTime: '14:00' },
      ],
    });

    expect(facts.range).toBe('Thu 8 – Sun 11 Oct');
    expect(facts.appointments.map((item) => item.text)).toEqual([
      'Sat 10 Oct · from 15:00',
      'Sun 11 Oct · from 14:00',
    ]);
    expect(facts.selectedDatesOnly).toBe(false);
  });

  test('identical daily hours collapse to one line', () => {
    const facts = whenFacts({
      ...base,
      startDate: '2026-10-09',
      endDate: '2026-10-11',
      scheduleConfidence: 'continuous',
      occurrences: ['09', '10', '11'].map((day) => ({
        date: `2026-10-${day}`,
        startTime: '11:00',
        endTime: '21:00',
      })),
    });

    expect(facts.appointments).toEqual([]);
    expect(facts.range).toBe('Fri 9 – Sun 11 Oct · daily 11:00–21:00');
  });

  test('sparse appointments are selected dates, never a block', () => {
    const facts = whenFacts({
      ...base,
      startDate: '2026-10-09',
      endDate: '2026-11-07',
      scheduleConfidence: 'discrete',
      occurrences: [
        { date: '2026-10-10', startTime: '18:00' },
        { date: '2026-10-16', startTime: '18:00' },
      ],
    });

    expect(facts.selectedDatesOnly).toBe(true);
    expect(facts.range).toBe('Fri 9 Oct – Sat 7 Nov');
    expect(facts.appointments.map((item) => item.text)).toEqual([
      'Sat 10 Oct · from 18:00',
      'Fri 16 Oct · from 18:00',
    ]);
  });

  test('unparsed hours keep the source wording', () => {
    const facts = whenFacts({
      ...base,
      startDate: '2026-10-11',
      endDate: '2026-10-18',
      scheduleConfidence: 'unknown',
      hoursText: '11.10.2026 bis 18.10.2026 ab 08:00 bis 17:00 Uhr sonntags',
    });

    expect(facts.range).toBe('Sun 11 – Sun 18 Oct');
    expect(facts.appointments).toEqual([]);
    expect(facts.sourceHours).toBe(
      '11.10.2026 bis 18.10.2026 ab 08:00 bis 17:00 Uhr sonntags',
    );
  });

  test('legacy exports without schedule evidence show the dates only', () => {
    expect(whenFacts(base)).toEqual({
      range: 'Sat 10 Oct',
      appointments: [],
      selectedDatesOnly: false,
      sourceHours: null,
    });
  });

  test('midnight reads as a word', () => {
    const facts = whenFacts({
      ...base,
      scheduleConfidence: 'continuous',
      occurrences: [{ date: '2026-10-10', startTime: '20:00', endTime: '24:00' }],
    });

    expect(facts.appointments[0].text).toBe('Sat 10 Oct · 20:00–midnight');
  });
});

describe('place and entry', () => {
  const place = {
    venue: 'Tiergarten',
    street: 'Tiergartenstraße 117',
    postalCode: '30559',
    locality: 'Hannover',
    municipality: 'Hannover',
  };

  test('a known address gets an OpenStreetMap search', () => {
    expect(placeAddress(place)).toBe('Tiergartenstraße 117, 30559 Hannover');
    expect(mapUrl(place)).toBe(
      'https://www.openstreetmap.org/search?query=Tiergartenstra%C3%9Fe%20117%2C%2030559%20Hannover',
    );
  });

  test('prices read in English; free stays tied to its row', () => {
    expect(entryPrice('free')).toBe('free');
    expect(entryPrice('€3.50')).toBe('€3.50');
  });
});

describe('onwardOccasions', () => {
  // An explicit Berlin clock: build-time selection must respect hours too.
  const today = new Date('2026-10-10T12:00:00+02:00');
  const slugs = (result: ReturnType<typeof onwardOccasions>) =>
    result.entries.map((entry) => entry.occasion.slug);

  test('excludes itself, cancelled, undated postponed and ended occasions', () => {
    const current = occasion('current');
    const result = onwardOccasions(
      current,
      [
        current,
        occasion('cancelled', { sourceStatus: 'cancelled' }),
        occasion('postponed', { sourceStatus: 'postponed' }),
        occasion('ended', { startDate: '2026-10-01', endDate: '2026-10-09' }),
        occasion('rescheduled', {
          sourceStatus: 'rescheduled',
          startDate: '2026-10-20',
          endDate: '2026-10-20',
          previousStartDate: '2026-10-12',
        }),
      ],
      today,
    );

    expect(slugs(result)).toEqual(['rescheduled']);
  });

  test('a sparse schedule without remaining dates is not current', () => {
    const result = onwardOccasions(
      occasion('current'),
      [
        occasion('exhausted', {
          startDate: '2026-10-01',
          endDate: '2026-11-07',
          scheduleConfidence: 'discrete',
          occurrences: [{ date: '2026-10-02', startTime: '18:00' }],
        }),
      ],
      today,
    );

    expect(result).toEqual({ entries: [], day: null, sameDayCount: 0 });
  });

  const saturday = occasion('current', { startDate: '2026-10-17', endDate: '2026-10-17' });
  const seasonHours = { date: '2026-10-17', startTime: '11:00', endTime: '21:00' };
  const candidates = [
    occasion('soon-weekday', { startDate: '2026-10-13', endDate: '2026-10-13' }),
    occasion('same-sunday', { startDate: '2026-10-18', endDate: '2026-10-18' }),
    occasion('sparse-season-same-day', {
      startDate: '2026-10-09',
      endDate: '2026-11-07',
      scheduleConfidence: 'discrete',
      occurrences: [
        { date: '2026-10-16', startTime: '18:00' },
        { date: '2026-10-17', startTime: '18:00' },
      ],
    }),
    occasion('season-same-day', {
      startDate: '2026-10-01',
      endDate: '2026-10-31',
      scheduleConfidence: 'continuous',
      occurrences: [seasonHours],
    }),
    occasion('one-off-same-day', { startDate: '2026-10-17', endDate: '2026-10-17' }),
  ];

  test.each([
    {
      id: 'open on the same date first, one-offs before season-long, then by time',
      limit: 3,
      expected: ['one-off-same-day', 'season-same-day', 'sparse-season-same-day'],
      day: '2026-10-17',
    },
    {
      id: 'a row not open that day drops the shared-day heading',
      limit: 4,
      expected: ['one-off-same-day', 'season-same-day', 'sparse-season-same-day', 'soon-weekday'],
      day: null,
    },
  ])('$id', ({ limit, expected, day }) => {
    const result = onwardOccasions(saturday, candidates, today, limit);

    expect(slugs(result)).toEqual(expected);
    expect(result.day).toBe(day);
    expect(result.sameDayCount).toBe(3);
    // Each row carries that day's hours, not the season's next opening.
    expect(result.entries[1].appointment).toEqual(seasonHours);
  });

  test('an occasion that closed earlier today is no longer onward', () => {
    const current = occasion('current', { startDate: '2026-10-11', endDate: '2026-10-11' });
    const closesAt1830 = occasion('closes-at-1830', {
      startDate: '2026-10-10',
      endDate: '2026-10-10',
      scheduleConfidence: 'continuous',
      occurrences: [{ date: '2026-10-10', startTime: '13:00', endTime: '18:30' }],
    });
    const at = (time: string) => new Date(`2026-10-10T${time}:00+02:00`);

    expect(slugs(onwardOccasions(current, [closesAt1830], at('14:00')))).toEqual(['closes-at-1830']);
    expect(slugs(onwardOccasions(current, [closesAt1830], at('19:00')))).toEqual([]);
  });
});

describe('tileAppointment', () => {
  const now = new Date('2026-10-10T12:00:00+02:00');

  test.each([
    { id: 'timed next date', extra: { startDate: '2026-10-12', endDate: '2026-10-20', scheduleConfidence: 'continuous' as const, occurrences: [{ date: '2026-10-12', startTime: '11:00', endTime: '21:00' }] }, face: { weekday: 'Mon', day: '12', month: 'Oct', hours: '11:00–21:00' } },
    { id: 'single day without hours', extra: { startDate: '2026-10-11', endDate: '2026-10-11' }, face: { weekday: 'Sun', day: '11', month: 'Oct', hours: 'Sun 11 Oct' } },
    { id: 'unknown multi-day run', extra: { startDate: '2026-10-11', endDate: '2026-10-13' }, face: null },
    { id: 'cancelled', extra: { sourceStatus: 'cancelled' as const }, face: null },
    { id: 'ended', extra: { startDate: '2026-10-01', endDate: '2026-10-09' }, face: null },
    { id: 'next date beyond the horizon', extra: { startDate: '2026-11-10', endDate: '2026-11-10' }, face: null },
  ])('$id', ({ extra, face }) => {
    const appointment = tileAppointment(occasion('tile', extra), now);
    expect(appointment ? tileFace(appointment) : null).toEqual(face);
  });
});
