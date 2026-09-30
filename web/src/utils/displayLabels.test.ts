import { describe, expect, test } from 'bun:test';
import { formatEventTime, formatFskRating } from './displayLabels';

describe('formatEventTime', () => {
  test('shows the German end-of-day 24:00 as midnight', () => {
    expect(formatEventTime('24:00')).toBe('midnight');
  });

  test('leaves ordinary times untouched', () => {
    expect(formatEventTime('20:00')).toBe('20:00');
    expect(formatEventTime('00:30')).toBe('00:30');
  });
});

describe('formatFskRating', () => {
  test('adds a space and a plus to the age limit', () => {
    expect(formatFskRating('FSK12')).toBe('FSK 12+');
    expect(formatFskRating('FSK16')).toBe('FSK 16+');
    expect(formatFskRating('FSK 6')).toBe('FSK 6+');
  });

  test('keeps an unrecognised rating as published', () => {
    expect(formatFskRating('ohne Angabe')).toBe('ohne Angabe');
  });
});
