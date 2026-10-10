import type {
  OccasionOccurrence,
  OccasionPlace,
  OccasionSummary,
} from '../data/types';
import { formatEventTime } from './displayLabels';
import {
  OCCASION_HORIZON_DAYS,
  berlinClock,
  occasionIsCurrent,
} from './occasionStatus';

// Pure helpers for the occasion detail sheet (#54). They read only exported
// facts; anything the source did not state is left out, never guessed.

const DAY_MS = 86_400_000;

function utcDate(isoDate: string): Date {
  const [year, month, day] = isoDate.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function addDays(isoDate: string, days: number): string {
  return new Date(utcDate(isoDate).getTime() + days * DAY_MS)
    .toISOString()
    .slice(0, 10);
}

function format(isoDate: string, options: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', ...options })
    .format(utcDate(isoDate));
}

/** "Sat 10 Oct", "Thu 8 – Sun 11 Oct" or "Fri 9 Oct – Sat 7 Nov". */
export function sheetDateLine({
  startDate,
  endDate,
}: Pick<OccasionSummary, 'startDate' | 'endDate'>): string {
  const day = { weekday: 'short', day: 'numeric' } as const;
  const full = { ...day, month: 'short' } as const;
  if (startDate === endDate) return format(startDate, full);
  if (startDate.slice(0, 4) !== endDate.slice(0, 4)) {
    // en-GB puts a comma after the weekday once a year is added.
    return (
      `${format(startDate, full)} ${startDate.slice(0, 4)} – ` +
      `${format(endDate, full)} ${endDate.slice(0, 4)}`
    );
  }
  if (startDate.slice(0, 7) === endDate.slice(0, 7)) {
    return `${format(startDate, day)} – ${format(endDate, full)}`;
  }
  return `${format(startDate, full)} – ${format(endDate, full)}`;
}

function hours({ startTime, endTime }: OccasionOccurrence): string | null {
  if (!startTime) return null;
  return endTime
    ? `${formatEventTime(startTime)}–${formatEventTime(endTime)}`
    : `from ${formatEventTime(startTime)}`;
}

export interface Appointment {
  date: string;
  datetime: string;
  text: string;
}

export interface WhenFacts {
  /** Overall dates; null when the single appointment already says it. */
  range: string | null;
  appointments: Appointment[];
  /** Sparse schedule: only the listed dates, never the days between. */
  selectedDatesOnly: boolean;
  /** Source wording the parser could not confirm, shown as German. */
  sourceHours: string | null;
}

/**
 * The When row. Confirmed appointments are listed with their hours; a
 * continuous run with identical hours every day collapses to one line; an
 * unparsed schedule keeps the source's own wording.
 */
export function whenFacts(occasion: OccasionSummary): WhenFacts {
  const range = sheetDateLine(occasion);
  const parsed =
    occasion.scheduleConfidence === 'continuous' ||
    occasion.scheduleConfidence === 'discrete';
  const occurrences = parsed ? occasion.occurrences ?? [] : [];
  const selectedDatesOnly = occasion.scheduleConfidence === 'discrete';
  const sourceHours =
    occasion.scheduleConfidence === 'unknown' && occasion.hoursText
      ? occasion.hoursText
      : null;

  const timed = occurrences.some((occurrence) => occurrence.startTime);
  if (!selectedDatesOnly && !timed) {
    return { range, appointments: [], selectedDatesOnly, sourceHours };
  }

  const daily = new Set(occurrences.map(hours));
  if (!selectedDatesOnly && occurrences.length > 1 && daily.size === 1) {
    return {
      range: `${range} · daily ${hours(occurrences[0])}`,
      appointments: [],
      selectedDatesOnly,
      sourceHours,
    };
  }

  const appointments = occurrences.map((occurrence) => {
    const time = hours(occurrence);
    const day = format(occurrence.date, {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
    });
    return {
      date: occurrence.date,
      datetime: occurrence.startTime
        ? `${occurrence.date}T${occurrence.startTime}`
        : occurrence.date,
      text: time ? `${day} · ${time}` : day,
    };
  });
  const single =
    occasion.startDate === occasion.endDate && appointments.length === 1;
  return {
    range: single ? null : range,
    appointments,
    selectedDatesOnly,
    sourceHours,
  };
}

/** One-line postal address for copying and map search. */
export function placeAddress(place: OccasionPlace): string {
  return `${place.street}, ${place.postalCode} ${place.locality}`;
}

/** OpenStreetMap search for an official address; the map offers directions. */
export function mapUrl(place: OccasionPlace): string {
  return `https://www.openstreetmap.org/search?query=${encodeURIComponent(
    placeAddress(place),
  )}`;
}

/** Entry price in English; "free" stays attached to its own condition row. */
export function entryPrice(price: string): string {
  return price === 'free' ? 'free' : price;
}

/**
 * Dates on which an occasion is current from `today`: its remaining
 * confirmed appointments if sparse, otherwise its envelope inside the
 * inclusive today..today+14 horizon.
 */
function currentDates(occasion: OccasionSummary, today: string): string[] {
  if (occasion.scheduleConfidence === 'discrete') {
    return (occasion.occurrences ?? [])
      .map((occurrence) => occurrence.date)
      .filter((date) => date >= today);
  }
  const first = occasion.startDate > today ? occasion.startDate : today;
  const horizon = addDays(today, OCCASION_HORIZON_DAYS);
  const last = occasion.endDate < horizon ? occasion.endDate : horizon;
  const dates: string[] = [];
  for (let date = first; date <= last; date = addDays(date, 1)) dates.push(date);
  return dates;
}

/** The Saturday of a weekend date, so Saturday and Sunday match. */
function weekendOf(date: string): string | null {
  const weekday = utcDate(date).getUTCDay();
  if (weekday === 6) return date;
  if (weekday === 0) return addDays(date, -1);
  return null;
}

/**
 * Up to three other current occasions at `now` for onward discovery.
 * Cancelled, undated postponed, ended and exhausted sparse occasions are
 * left out, including one whose last appointment closed earlier today.
 * Those sharing a date or a weekend with this one come first, then by
 * next date.
 */
export function onwardOccasions(
  current: OccasionSummary,
  occasions: OccasionSummary[],
  now: Date,
  limit = 3,
): OccasionSummary[] {
  const today = berlinClock(now).date;
  const own = currentDates(current, today);
  const ownDays = new Set(own);
  const ownWeekends = new Set(own.map(weekendOf).filter(Boolean));
  return occasions
    .filter(
      (occasion) =>
        occasion.id !== current.id &&
        occasion.sourceStatus !== 'cancelled' &&
        occasion.sourceStatus !== 'postponed' &&
        occasionIsCurrent(occasion, now),
    )
    .map((occasion) => {
      const dates = currentDates(occasion, today);
      const overlaps = dates.some(
        (date) => ownDays.has(date) || ownWeekends.has(weekendOf(date)),
      );
      return { occasion, next: dates[0], overlaps };
    })
    .filter((candidate) => candidate.next !== undefined)
    .sort(
      (left, right) =>
        Number(right.overlaps) - Number(left.overlaps) ||
        left.next.localeCompare(right.next) ||
        left.occasion.name.localeCompare(right.occasion.name),
    )
    .slice(0, limit)
    .map((candidate) => candidate.occasion);
}
