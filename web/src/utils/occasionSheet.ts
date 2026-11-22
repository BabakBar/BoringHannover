import type {
  OccasionOccurrence,
  OccasionPlace,
  OccasionSummary,
} from '../data/types';
import { formatEventTime } from './displayLabels';
import {
  OCCASION_HORIZON_DAYS,
  addDays,
  appointmentOn,
  berlinClock,
  nextAppointment,
  occasionHasEnded,
  occasionIsCurrent,
  type OccasionSchedule,
} from './occasionStatus';

// Pure helpers for occasion views (#54). They read only exported
// facts; anything the source did not state is left out, never guessed.

function utcDate(isoDate: string): Date {
  const [year, month, day] = isoDate.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day));
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

export function appointmentHours({ startTime, endTime }: OccasionOccurrence): string | null {
  if (!startTime) return null;
  return endTime
    ? `${formatEventTime(startTime)}–${formatEventTime(endTime)}`
    : `from ${formatEventTime(startTime)}`;
}

/** "Sat 10 Oct · 13:00–18:30", or the day alone without confirmed hours. */
export function appointmentText(occurrence: OccasionOccurrence): string {
  const day = format(occurrence.date, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
  const time = appointmentHours(occurrence);
  return time ? `${day} · ${time}` : day;
}

/** The homepage's next supported date, with the whole run kept as context. */
export function spotlightDates(
  occasion: OccasionSchedule,
  now: Date,
): { when: string; span: string | null } {
  const unavailable =
    occasion.sourceStatus === 'cancelled' || occasion.sourceStatus === 'postponed';
  const next = unavailable ? null : nextAppointment(occasion, now);
  const appointment =
    next && next.date <= addDays(berlinClock(now).date, OCCASION_HORIZON_DAYS)
      ? next
      : null;
  return {
    when: appointment
      ? appointmentText(appointment)
      : !unavailable && occasionHasEnded(occasion, now)
        ? 'Ended'
        : 'Check source for dates',
    span: appointment && occasion.startDate === occasion.endDate
      ? null
      : `${occasion.scheduleConfidence === 'discrete' ? 'Selected dates · ' : ''}${sheetDateLine(occasion)}`,
  };
}

/**
 * The detail's date tile: the same appointment as the When row, so none for
 * cancelled, postponed or ended occasions, an unparsed multi-day run or a
 * next date beyond the horizon.
 */
export function tileAppointment(occasion: OccasionSchedule, now: Date): OccasionOccurrence | null {
  const parsed = occasion.scheduleConfidence === 'continuous' ||
    occasion.scheduleConfidence === 'discrete' || occasion.startDate === occasion.endDate;
  if (!parsed || occasion.sourceStatus === 'cancelled' || occasion.sourceStatus === 'postponed') return null;
  const next = nextAppointment(occasion, now);
  return next && next.date <= addDays(berlinClock(now).date, OCCASION_HORIZON_DAYS) ? next : null;
}

/** "SAT" / "28" / "NOV" (uppercased by CSS) and the hours, or the date without them. */
export function tileFace(appointment: OccasionOccurrence) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' })
      .formatToParts(utcDate(appointment.date))
      .map((part) => [part.type, part.value]),
  );
  return {
    weekday: parts.weekday,
    day: parts.day,
    month: parts.month,
    hours: appointmentHours(appointment) ?? format(appointment.date, { weekday: 'short', day: 'numeric', month: 'short' }),
  };
}

/** The detail's date emphasis; an unparsed multi-day envelope is not an appointment. */
export function sheetNextDate(occasion: OccasionSchedule, now: Date): string {
  const parsed =
    occasion.scheduleConfidence === 'continuous' ||
    occasion.scheduleConfidence === 'discrete';
  if (!parsed && occasion.startDate !== occasion.endDate && !occasionHasEnded(occasion, now)) {
    return 'Check source for dates';
  }
  return spotlightDates(occasion, now).when;
}

interface Appointment {
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

  const daily = new Set(occurrences.map(appointmentHours));
  if (
    !selectedDatesOnly && occurrences.length > 1 && daily.size === 1 &&
    occurrences[0].date === occasion.startDate &&
    occurrences.at(-1)!.date === occasion.endDate &&
    addDays(occasion.startDate, occurrences.length - 1) === occasion.endDate
  ) {
    return {
      range: `${range} · daily ${appointmentHours(occurrences[0])}`,
      appointments: [],
      selectedDatesOnly,
      sourceHours,
    };
  }

  const appointments = occurrences.map((occurrence) => ({
    date: occurrence.date,
    datetime: occurrence.startTime
      ? `${occurrence.date}T${occurrence.startTime}`
      : occurrence.date,
    text: appointmentText(occurrence),
  }));
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
export function entryPrice(price: string, isFrom = false): string {
  return isFrom ? `from ${price}` : price;
}

/**
 * Dates on which an occasion is current from `today`: its remaining
 * confirmed appointments if sparse, otherwise its envelope inside the
 * inclusive today..today+30 horizon.
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

/** Season-long: runs for seven days or more, like the central Christmas market. */
export function isSeasonLong({ startDate, endDate }: Pick<OccasionSummary, 'startDate' | 'endDate'>): boolean {
  return addDays(startDate, 6) <= endDate;
}

function startMinutes(appointment: OccasionOccurrence | null): number {
  if (!appointment?.startTime) return 24 * 60;
  const [hour, minute] = appointment.startTime.split(':').map(Number);
  return hour * 60 + minute;
}

export interface OnwardEntry {
  occasion: OccasionSummary;
  /** On this occasion's next date when `sameDay`, otherwise the next one. */
  appointment: OccasionOccurrence | null;
  sameDay: boolean;
}

/**
 * Other current occasions at `now` for onward discovery. Cancelled, undated
 * postponed, ended and exhausted sparse occasions are left out, including one
 * whose last appointment closed earlier today. Those open on this occasion's
 * next date come first, then one-offs before season-long ones, then by next
 * date and time. `day` is that date when every shown entry is open on it.
 */
export function onwardOccasions(
  current: OccasionSummary,
  occasions: OccasionSummary[],
  now: Date,
  limit = 3,
): { entries: OnwardEntry[]; day: string | null; sameDayCount: number } {
  const today = berlinClock(now).date;
  const ownNext = nextAppointment(current, now)?.date ?? null;
  const ranked = occasions
    .filter(
      (occasion) =>
        occasion.id !== current.id &&
        occasion.sourceStatus !== 'cancelled' &&
        occasion.sourceStatus !== 'postponed' &&
        occasionIsCurrent(occasion, now) &&
        currentDates(occasion, today).length > 0,
    )
    .map((occasion) => {
      const onDay = ownNext ? appointmentOn(occasion, ownNext, now) : null;
      return {
        occasion,
        appointment: onDay ?? nextAppointment(occasion, now),
        sameDay: onDay !== null,
        season: isSeasonLong(occasion),
      };
    })
    .sort(
      (left, right) =>
        Number(right.sameDay) - Number(left.sameDay) ||
        Number(left.season) - Number(right.season) ||
        (left.appointment?.date ?? '').localeCompare(right.appointment?.date ?? '') ||
        startMinutes(left.appointment) - startMinutes(right.appointment) ||
        left.occasion.name.localeCompare(right.occasion.name, 'de'),
    );
  const entries = ranked
    .slice(0, limit)
    .map(({ occasion, appointment, sameDay }) => ({ occasion, appointment, sameDay }));
  const sameDayCount = ranked.filter((entry) => entry.sameDay).length;
  return {
    entries,
    day: entries.length > 0 && entries.every((entry) => entry.sameDay) ? ownNext : null,
    sameDayCount,
  };
}
