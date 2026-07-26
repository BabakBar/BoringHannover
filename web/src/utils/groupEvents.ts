// Group concerts by date for timeline display
import type { Concert } from '../data/types';

export interface EventGroup {
  dateKey: string;      // "30 Nov" - for grouping
  day: string;          // "So"
  dayNum: string;       // "30"
  month: string;        // "Nov"
  year?: string;        // "2026" or undefined
  events: Concert[];
}

/**
 * Group concerts by their date string.
 * Preserves original order (already chronological from scraper).
 */
export function groupEventsByDate(concerts: Concert[]): EventGroup[] {
  const groups: Map<string, EventGroup> = new Map();

  for (const concert of concerts) {
    const dateKey = concert.date; // "30 Nov" or "13 Jan 2026"

    if (!groups.has(dateKey)) {
      const dateParts = dateKey.split(' ');
      groups.set(dateKey, {
        dateKey,
        day: concert.day,
        dayNum: dateParts[0],
        month: dateParts[1],
        year: dateParts[2], // undefined if not present
        events: []
      });
    }

    groups.get(dateKey)!.events.push(concert);
  }

  return Array.from(groups.values());
}

/**
 * Keep the visible timeline within its event budget.
 *
 * A large first day is split across visible and overflow groups instead of
 * collapsing the entire timeline into one "more" control.
 */
export function sliceEventGroups(
  groups: EventGroup[],
  targetCount: number
): { visible: EventGroup[]; overflow: EventGroup[] } {
  const visible: EventGroup[] = [];
  const overflow: EventGroup[] = [];
  let eventCount = 0;

  for (const group of groups) {
    const remaining = Math.max(0, targetCount - eventCount);

    if (remaining === 0) {
      overflow.push(group);
    } else if (group.events.length <= remaining) {
      visible.push(group);
      eventCount += group.events.length;
    } else {
      visible.push({
        ...group,
        events: group.events.slice(0, remaining),
      });
      overflow.push({
        ...group,
        events: group.events.slice(remaining),
      });
      eventCount += remaining;
    }
  }

  return { visible, overflow };
}
