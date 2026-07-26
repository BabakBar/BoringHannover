import type { Concert } from '../data/types';

export type OccasionMode = 'all' | 'today' | 'tonight' | 'weekend';

export interface OccasionFilters {
  mode: OccasionMode;
  date: string;
  category: string;
  venue: string;
}

function toLocalISO(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function getWeekendDates(now: Date): Set<string> {
  const dates = new Set<string>();
  const day = now.getDay();

  if (day === 0) {
    dates.add(toLocalISO(now));
    return dates;
  }

  const daysUntilSaturday = day === 6 ? 0 : 6 - day;
  const saturday = new Date(now);
  saturday.setDate(now.getDate() + daysUntilSaturday);
  const sunday = new Date(saturday);
  sunday.setDate(saturday.getDate() + 1);

  dates.add(toLocalISO(saturday));
  dates.add(toLocalISO(sunday));
  return dates;
}

export function matchesOccasionFilters(
  event: Concert,
  filters: OccasionFilters,
  now: Date,
): boolean {
  const eventDate = event.dateISO ?? '';
  const today = toLocalISO(now);

  if (filters.mode === 'today' && eventDate !== today) return false;
  if (
    filters.mode === 'tonight'
    && (eventDate !== today || !event.time || event.time < '17:00')
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
