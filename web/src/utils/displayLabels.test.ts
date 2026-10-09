import { expect, test } from 'bun:test';
import { formatEventTime, formatFskRating } from './displayLabels';

test('formatEventTime shows the German end-of-day 24:00 as midnight', () => {
  expect(formatEventTime('24:00')).toBe('midnight');
  expect(formatEventTime('20:00')).toBe('20:00');
  expect(formatEventTime('00:30')).toBe('00:30');
});

test('formatFskRating adds a space and a plus, keeping unknown ratings', () => {
  expect(formatFskRating('FSK12')).toBe('FSK 12+');
  expect(formatFskRating('FSK 6')).toBe('FSK 6+');
  expect(formatFskRating('ohne Angabe')).toBe('ohne Angabe');
});
