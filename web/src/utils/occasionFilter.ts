import type { Concert } from '../data/types';
import { addDays, berlinClock } from './occasionStatus';

export type OccasionMode = 'all' | 'today' | 'tonight' | 'weekend';

export interface OccasionFilters {
  mode: OccasionMode;
  date: string;
  category: string;
  venue: string;
}

export function getWeekendDates(now: Date): Set<string> {
  const today = berlinClock(now).date;
  // The weekday belongs to the Berlin calendar date, independent of the
  // visitor's timezone. Calendar arithmetic also avoids 23/25-hour DST days.
  const day = new Date(`${today}T12:00:00Z`).getUTCDay();
  if (day === 0) return new Set([today]);
  const daysUntilSaturday = day === 6 ? 0 : 6 - day;
  const saturday = addDays(today, daysUntilSaturday);
  return new Set([saturday, addDays(saturday, 1)]);
}

export function matchesOccasionFilters(
  event: Concert,
  filters: OccasionFilters,
  now: Date,
): boolean {
  const eventDate = event.dateISO ?? '';
  const today = berlinClock(now).date;

  if (filters.mode === 'today' && eventDate !== today) return false;
  if (
    filters.mode === 'tonight'
    && (
      eventDate !== today || !event.time || event.time < '17:00'
      || event.timeConfidence === 'fallback'
    )
  ) {
    return false;
  }
  if (
    filters.mode === 'weekend'
    && !getWeekendDates(now).has(eventDate)
  ) {
    return false;
  }
  if (filters.date !== 'all' && eventDate !== filters.date) return false;
  if (
    filters.category !== 'all'
    && event.programmeCategory !== filters.category
  ) {
    return false;
  }
  return filters.venue === 'all' || event.venue === filters.venue;
}
