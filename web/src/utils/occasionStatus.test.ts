import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { OccasionSchedule } from './occasionStatus';
import {
  berlinClock,
  occasionLabel,
  staticOccasionLabel,
} from './occasionStatus';

interface ClockCase {
  name: string;
  now: string;
  occasion: OccasionSchedule;
  expected: { lifecycle: string | null; label: string; staticLabel: string };
}

// Shared with tests/test_occasion_temporal.py so Python and the UI agree on
// the same clocks; the expected Python lifecycle and UI label differ on purpose.
const { cases } = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL('../../../tests/fixtures/occasion_clock_cases.json', import.meta.url),
    ),
    'utf8',
  ),
) as { cases: ClockCase[] };

describe('shared occasion clock fixture', () => {
  for (const { name, now, occasion, expected } of cases) {
    test(name, () => {
      expect(occasionLabel(occasion, new Date(now)).text).toBe(expected.label);
      expect(staticOccasionLabel(occasion, new Date(now)).text).toBe(
        expected.staticLabel,
      );
    });
  }
});

describe('berlinClock', () => {
  test('uses the Berlin calendar date and follows the DST change', () => {
    expect(berlinClock(new Date('2026-10-09T22:30:00Z'))).toEqual({
      date: '2026-10-10',
      minutes: 30,
    });
    expect(berlinClock(new Date('2026-10-25T00:30:00Z'))).toEqual({
      date: '2026-10-25',
      minutes: 2 * 60 + 30,
    });
    expect(berlinClock(new Date('2026-10-25T01:30:00Z'))).toEqual({
      date: '2026-10-25',
      minutes: 2 * 60 + 30,
    });
  });
});

describe('labels never invent schedule facts', () => {
  const envelope: OccasionSchedule = {
    startDate: '2026-10-09',
    endDate: '2026-10-11',
  };

  test('an envelope without occurrences is Running at any hour', () => {
    for (const hour of ['06', '12', '21']) {
      expect(
        occasionLabel(envelope, new Date(`2026-10-10T${hour}:00:00Z`)).key,
      ).toBe('running');
    }
  });

  test('occurrences without a parsed schedule are not treated as confirmed', () => {
    const occasion: OccasionSchedule = {
      startDate: '2026-10-10',
      endDate: '2026-10-10',
      occurrences: [{ date: '2026-10-10', startTime: '13:00', endTime: '18:30' }],
      scheduleConfidence: 'unknown',
    };
    expect(occasionLabel(occasion, new Date('2026-10-10T12:00:00Z')).key).toBe(
      'running',
    );
  });

  test('build-time labels never use the hour or relative days', () => {
    const occasion: OccasionSchedule = {
      startDate: '2026-10-10',
      endDate: '2026-10-10',
      occurrences: [{ date: '2026-10-10', startTime: '13:00', endTime: '18:30' }],
      scheduleConfidence: 'continuous',
    };
    const keys = new Set(
      ['2026-10-09T10:00:00Z', '2026-10-10T12:00:00Z', '2026-10-11T12:00:00Z'].map(
        (now) => staticOccasionLabel(occasion, new Date(now)).key,
      ),
    );
    expect([...keys].sort()).toEqual(['ended', 'running', 'upcoming']);
  });
});
