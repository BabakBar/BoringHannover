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
  test('matches combined date, category, and venue filters', () => {
    expect(matchesOccasionFilters(
      event,
      {
        ...allFilters,
        date: '2026-07-31',
        category: 'Music',
        venue: 'Maschsee-Bühne',
      },
      new Date(2026, 6, 31, 12),
    )).toBe(true);

    expect(matchesOccasionFilters(
      event,
      { ...allFilters, category: 'Family' },
      new Date(2026, 6, 31, 12),
    )).toBe(false);
  });

  test('tonight requires today and a reliable evening time', () => {
    expect(matchesOccasionFilters(
      event,
      { ...allFilters, mode: 'tonight' },
      new Date(2026, 6, 31, 12),
    )).toBe(true);

    expect(matchesOccasionFilters(
      { ...event, time: null },
      { ...allFilters, mode: 'tonight' },
      new Date(2026, 6, 31, 12),
    )).toBe(false);
  });

  test('weekend means the nearest remaining weekend', () => {
    expect([...getWeekendDates(new Date(2026, 6, 30, 12))]).toEqual([
      '2026-08-01',
      '2026-08-02',
    ]);
    expect([...getWeekendDates(new Date(2026, 7, 2, 12))]).toEqual([
      '2026-08-02',
    ]);
  });
});
