import { expect, test } from 'bun:test';
import { eventStatusLabel, isCancelledStatus } from './eventStatus';

test('every published change status has a label; no evidence has none', () => {
  expect(eventStatusLabel('cancelled')).toBe('Cancelled');
  expect(eventStatusLabel('canceled')).toBe('Cancelled');
  expect(eventStatusLabel('postponed')).toBe('Postponed');
  expect(eventStatusLabel('rescheduled')).toBe('Rescheduled');
  expect(eventStatusLabel('sold_out')).toBe('Sold Out');
  for (const status of ['available', 'unknown', '', null, undefined, 'other']) {
    expect(eventStatusLabel(status)).toBeUndefined();
  }
  expect(isCancelledStatus('canceled')).toBe(true);
  expect(isCancelledStatus('postponed')).toBe(false);
});
