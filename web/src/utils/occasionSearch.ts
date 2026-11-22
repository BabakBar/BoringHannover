import type { OccasionSummary } from '../data/types';
import { appointmentHours } from './occasionSheet';
import { addDays } from './occasionStatus';

// Search titles and descriptions from absolute facts only: search engines
// cache snippets for weeks, so "today", "next" or "in N days" would go stale.

function format(isoDate: string, options: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', ...options })
    .format(new Date(`${isoDate}T00:00:00Z`));
}

const DAY_MONTH = { day: 'numeric', month: 'short' } as const;
const LONG = { day: 'numeric', month: 'long', year: 'numeric' } as const;

/** The exporter's fallback (exporters._occasion_description) says nothing the page doesn't. */
export function isFallbackDescription(description: string | null | undefined): boolean {
  return !description || description.endsWith('See the source for details.');
}

/** "Sat 5 Dec 2026", "23 Nov – 22 Dec 2026" or "12 Nov 2026 – 31 Jan 2027". */
export function titleDates({ startDate, endDate }: Pick<OccasionSummary, 'startDate' | 'endDate'>): string {
  if (startDate === endDate) {
    // en-GB puts a comma after the weekday once a year is added.
    return format(startDate, { weekday: 'short', ...DAY_MONTH, year: 'numeric' }).replace(',', '');
  }
  if (startDate.slice(0, 4) === endDate.slice(0, 4)) {
    return `${format(startDate, DAY_MONTH)} – ${format(endDate, { ...DAY_MONTH, year: 'numeric' })}`;
  }
  return `${format(startDate, { ...DAY_MONTH, year: 'numeric' })} – ${format(endDate, { ...DAY_MONTH, year: 'numeric' })}`;
}

export function searchTitle(occasion: OccasionSummary): string {
  const base = `${occasion.name} · ${titleDates(occasion)}`;
  const place = occasion.area === 'region' && occasion.place?.municipality
    ? occasion.place.municipality
    : 'Hannover';
  const withPlace = `${base} · ${place}`;
  return occasion.name.includes(place) || withPlace.length > 65 ? base : withPlace;
}

function whenSentence(occasion: OccasionSummary): string {
  const parsed = occasion.scheduleConfidence === 'continuous' || occasion.scheduleConfidence === 'discrete';
  const occurrences = parsed ? occasion.occurrences ?? [] : [];
  if (occasion.startDate === occasion.endDate) {
    const hours = occurrences[0] ? appointmentHours(occurrences[0]) : null;
    const day = format(occasion.startDate, { weekday: 'long', ...LONG }).replace(',', '');
    return hours ? `${day}, ${hours}` : day;
  }
  if (occasion.scheduleConfidence === 'discrete') {
    return `Selected dates from ${format(occasion.startDate, LONG)} to ${format(occasion.endDate, LONG)}`;
  }
  const range = occasion.startDate.slice(0, 4) === occasion.endDate.slice(0, 4)
    ? `${format(occasion.startDate, { day: 'numeric', month: 'long' })} – ${format(occasion.endDate, LONG)}`
    : `${format(occasion.startDate, LONG)} – ${format(occasion.endDate, LONG)}`;
  const hours = new Set(occurrences.map(appointmentHours));
  const [only] = hours;
  const everyDay = occurrences.length > 1 &&
    addDays(occasion.startDate, occurrences.length - 1) === occasion.endDate;
  return occasion.scheduleConfidence === 'continuous' && everyDay && hours.size === 1 && only
    ? `Daily ${only}, ${range}`
    : range;
}

/** Meta description: when, where, free entry, then any real About text. */
export function searchDescription(occasion: OccasionSummary, about: string | null): string {
  const status = occasion.sourceStatus === 'cancelled' ? 'Cancelled: '
    : occasion.sourceStatus === 'postponed' ? 'Postponed: '
    : '';
  const place = occasion.place
    ? [occasion.place.venue, occasion.place.street, `${occasion.place.postalCode} ${occasion.place.locality}`]
      .filter(Boolean).join(', ')
    : occasion.location;
  const admission = occasion.admission ?? [];
  const free = admission.length === 1 && admission[0].price === 'free' && !admission[0].label;
  return [
    `${status}${whenSentence(occasion)} at ${place}.`,
    free ? 'Free entry.' : '',
    about,
    occasion.programmeCount > 0 ? 'Explore the official programme by day, category, and location.' : '',
  ].filter(Boolean).join(' ');
}
