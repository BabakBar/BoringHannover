import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { OccasionSchedule } from './occasionStatus';
import {
  berlinClock,
  occasionHasEnded,
  occasionIsCurrent,
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

describe('expiry is independent of the source-status label', () => {
  const rescheduled: OccasionSchedule = {
    startDate: '2026-10-22',
    endDate: '2026-10-22',
    scheduleConfidence: 'continuous',
    occurrences: [{ date: '2026-10-22', startTime: '19:00', endTime: '22:00' }],
    sourceStatus: 'rescheduled',
  };
  const at = (iso: string) => new Date(iso);

  test('a rescheduled occasion ends although its label stays Rescheduled', () => {
    const after = at('2026-10-23T10:00:00+02:00');

    expect(occasionLabel(rescheduled, after).text).toBe('Rescheduled');
    expect(occasionHasEnded(rescheduled, after)).toBe(true);
    expect(occasionIsCurrent(rescheduled, after)).toBe(false);
    expect(occasionHasEnded(rescheduled, at('2026-10-22T21:00:00+02:00'))).toBe(
      false,
    );
  });

  test('the final confirmed appointment ending ends the occasion', () => {
    expect(occasionHasEnded(rescheduled, at('2026-10-22T22:30:00+02:00'))).toBe(
      true,
    );
  });

  test('an envelope runs through its last day', () => {
    const envelope: OccasionSchedule = {
      startDate: '2026-10-08',
      endDate: '2026-10-11',
    };

    expect(occasionHasEnded(envelope, at('2026-10-11T23:30:00+02:00'))).toBe(false);
    expect(occasionHasEnded(envelope, at('2026-10-12T00:10:00+02:00'))).toBe(true);
  });

  test('a sparse list without dates left is not current, even if rescheduled', () => {
    const sparse: OccasionSchedule = {
      startDate: '2026-10-09',
      endDate: '2026-11-07',
      scheduleConfidence: 'discrete',
      occurrences: [{ date: '2026-10-10', startTime: '18:00' }],
      sourceStatus: 'rescheduled',
    };
    const later = at('2026-10-20T12:00:00+02:00');

    expect(occasionHasEnded(sparse, later)).toBe(false);
    expect(occasionIsCurrent(sparse, later)).toBe(false);
    expect(occasionIsCurrent(sparse, at('2026-10-10T12:00:00+02:00'))).toBe(true);
  });
});
