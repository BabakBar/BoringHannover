import { describe, expect, test } from 'bun:test';
import type { Concert } from '../data/types';
import { groupEventsByDate, sliceEventGroups } from './groupEvents';

function event(title: string, date = '26 Jul'): Concert {
  return {
    title,
    date,
    dateISO: '2026-07-26',
    day: 'So',
    venue: 'Venue',
  };
}

describe('sliceEventGroups', () => {
  test('splits an oversized first day instead of emptying the timeline', () => {
    const events = Array.from(
      { length: 17 },
      (_, index) => event(`Event ${index + 1}`),
    );

    const result = sliceEventGroups(groupEventsByDate(events), 15);

    expect(result.visible).toHaveLength(1);
    expect(result.visible[0]?.events).toHaveLength(15);
    expect(result.overflow).toHaveLength(1);
    expect(result.overflow[0]?.events).toHaveLength(2);
  });

  test('preserves smaller complete days until the budget is reached', () => {
    const groups = groupEventsByDate([
      event('One'),
      event('Two'),
      event('Three', '27 Jul'),
    ]);

    const result = sliceEventGroups(groups, 2);

    expect(result.visible[0]?.events.map(item => item.title)).toEqual([
      'One',
      'Two',
    ]);
    expect(result.overflow[0]?.events[0]?.title).toBe('Three');
  });
});
