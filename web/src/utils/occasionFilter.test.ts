import { describe, expect, test } from 'bun:test';
import type { Concert } from '../data/types';
import {
  getWeekendDates,
  matchesOccasionFilters,
  type OccasionFilters,
} from './occasionFilter';

const event: Concert = {
  title: 'Lake concert',
  date: '31 Jul',
  dateISO: '2026-07-31',
  day: 'Fr',
  time: '20:00',
  venue: 'Maschsee-Bühne',
  programmeCategory: 'Music',
};

const allFilters: OccasionFilters = {
  mode: 'all',
  date: 'all',
  category: 'all',
  venue: 'all',
};

describe('occasion filters', () => {
  test('today and weekend use Berlin dates at midnight, DST and year boundaries', () => {
    for (const [instant, today, weekend] of [
      ['2026-07-31T22:30:00Z', '2026-08-01', ['2026-08-01', '2026-08-02']],
      ['2026-07-26T22:30:00Z', '2026-07-27', ['2026-08-01', '2026-08-02']],
      ['2026-03-28T23:30:00Z', '2026-03-29', ['2026-03-29']],
      ['2026-10-25T23:30:00Z', '2026-10-26', ['2026-10-31', '2026-11-01']],
      ['2026-12-31T23:30:00Z', '2027-01-01', ['2027-01-02', '2027-01-03']],
    ] as const) {
      const now = new Date(instant);
      expect(matchesOccasionFilters(
        { ...event, dateISO: today }, { ...allFilters, mode: 'today' }, now,
      ), instant).toBe(true);
      expect([...getWeekendDates(now)], instant).toEqual([...weekend]);
    }
  });

  test('a fallback time cannot qualify an appointment for Tonight', () => {
    expect(matchesOccasionFilters(
      { ...event, timeConfidence: 'fallback' },
      { ...allFilters, mode: 'tonight' },
      new Date('2026-07-31T12:00:00Z'),
    )).toBe(false);
  });

  test('matches combined date, category, and venue filters', () => {
    expect(matchesOccasionFilters(
      event,
      {
        ...allFilters,
        date: '2026-07-31',
        category: 'Music',
        venue: 'Maschsee-Bühne',
      },
      new Date('2026-07-31T10:00:00Z'),
    )).toBe(true);

    expect(matchesOccasionFilters(
      event,
      { ...allFilters, category: 'Family' },
      new Date('2026-07-31T10:00:00Z'),
    )).toBe(false);
  });

  test('tonight requires today and a reliable evening time', () => {
    expect(matchesOccasionFilters(
      event,
      { ...allFilters, mode: 'tonight' },
      new Date('2026-07-31T10:00:00Z'),
    )).toBe(true);

    expect(matchesOccasionFilters(
      { ...event, time: null },
      { ...allFilters, mode: 'tonight' },
      new Date('2026-07-31T10:00:00Z'),
    )).toBe(false);
  });

  test('weekend means the nearest remaining weekend', () => {
    expect([...getWeekendDates(new Date('2026-07-30T10:00:00Z'))]).toEqual([
      '2026-08-01',
      '2026-08-02',
    ]);
    expect([...getWeekendDates(new Date('2026-08-02T10:00:00Z'))]).toEqual([
      '2026-08-02',
    ]);
  });
});
