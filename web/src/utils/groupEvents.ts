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
 * Smart slice: returns complete day groups up to ~targetCount events.
 * Never splits a day group between visible/overflow.
 */
export function sliceEventGroups(
  groups: EventGroup[],
  targetCount: number
): { visible: EventGroup[]; overflow: EventGroup[] } {
  const visible: EventGroup[] = [];
  const overflow: EventGroup[] = [];
  let eventCount = 0;
  let reachedTarget = false;

  for (const group of groups) {
    if (!reachedTarget && eventCount + group.events.length <= targetCount) {
      visible.push(group);
      eventCount += group.events.length;
    } else if (!reachedTarget && eventCount < targetCount) {
      // This group would exceed target, but we haven't hit target yet
      // Include it to avoid tiny overflow, unless it's huge
      if (group.events.length <= 6) {
        visible.push(group);
        eventCount += group.events.length;
      }
      reachedTarget = true;
      if (group.events.length > 6) {
        overflow.push(group);
      }
    } else {
      overflow.push(group);
    }
  }

  return { visible, overflow };
}
