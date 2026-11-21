import type { OccasionOccurrence, OccasionSummary } from '../data/types';
import { appointmentHours, sheetDateLine } from './occasionSheet';
import {
  OCCASION_HORIZON_DAYS,
  addDays,
  appointmentOn,
  berlinClock,
  nextAppointment,
  occasionIsCurrent,
  type OccasionSchedule,
} from './occasionStatus';

// Redesign v2 experiment helpers (#54). Pure, clock as an argument, so the
// build and the browser share them.

type Named = OccasionSchedule & Pick<OccasionSummary, 'name'>;

/** Season-long: runs for 7 days or more, e.g. the central Christmas market. */
export function isSeasonLong(occasion: Pick<OccasionSummary, 'startDate' | 'endDate'>): boolean {
  return addDays(occasion.startDate, 6) <= occasion.endDate;
}

/** The exporter's fallback (exporters._occasion_description) says nothing the page doesn't. */
export function isFallbackDescription(description: string | null | undefined): boolean {
  return !description || description.endsWith('See the source for details.');
}

function utc(isoDate: string) {
  return new Date(`${isoDate}T00:00:00Z`);
}

function fmt(isoDate: string, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', ...options }).format(utc(isoDate));
}

export function minutesOf(time: string | null | undefined): number {
  if (!time) return 24 * 60;
  const [hour, minute] = time.split(':').map(Number);
  return hour * 60 + minute;
}

function byTimeThenName<T extends { name: string }>(
  left: { occasion: T; appointment: OccasionOccurrence | null },
  right: { occasion: T; appointment: OccasionOccurrence | null },
) {
  return minutesOf(left.appointment?.startTime) - minutesOf(right.appointment?.startTime) ||
    left.occasion.name.localeCompare(right.occasion.name, 'de');
}

function live(occasion: OccasionSchedule, now: Date) {
  return occasion.sourceStatus !== 'cancelled' && occasion.sourceStatus !== 'postponed' &&
    occasionIsCurrent(occasion, now);
}

/** Current occasions whose next appointment falls inside the 30-day horizon. */
export function currentOccasions<T extends Named>(occasions: readonly T[], now: Date): T[] {
  const horizon = addDays(berlinClock(now).date, OCCASION_HORIZON_DAYS);
  return occasions.filter(occasion => live(occasion, now) &&
    (nextAppointment(occasion, now)?.date ?? occasion.startDate) <= horizon);
}

export interface BoardRow<T> {
  occasion: T;
  appointment: OccasionOccurrence;
  /** Left column. */
  when: string;
  /** Right column. */
  end: string | null;
  now: boolean;
  opens: boolean;
}

/** Homepage board (concept A): today, then the next seven days. */
export function boardSelection<T extends Named>(occasions: readonly T[], now: Date) {
  const { date: today, minutes } = berlinClock(now);
  const current = currentOccasions(occasions, now);
  const todayEntries = current
    .map(occasion => ({ occasion, appointment: appointmentOn(occasion, today, now) }))
    .filter((entry): entry is { occasion: T; appointment: OccasionOccurrence } => entry.appointment !== null)
    .sort((left, right) =>
      Number(isSeasonLong(left.occasion)) - Number(isSeasonLong(right.occasion)) || byTimeThenName(left, right));
  const todayRows: BoardRow<T>[] = todayEntries.map(({ occasion, appointment }) => {
    const start = appointment.startTime ? minutesOf(appointment.startTime) : null;
    const open = start !== null && appointment.endTime !== undefined && appointment.endTime !== null &&
      minutes >= start && minutes < minutesOf(appointment.endTime);
    const when = open ? 'ON NOW'
      : !appointment.startTime ? 'TODAY'
      : start !== null && minutes >= start ? `FROM ${appointment.startTime}`
      : appointment.startTime;
    return { occasion, appointment, when, end: appointment.endTime ? `–${appointment.endTime}` : null, now: open, opens: false };
  });
  const inToday = new Set(todayEntries.map(entry => entry.occasion));
  const week = addDays(today, 7);
  const coming: BoardRow<T>[] = current
    .filter(occasion => !inToday.has(occasion) && (!isSeasonLong(occasion) || occasion.startDate > today))
    .map(occasion => ({ occasion, appointment: nextAppointment(occasion, now) }))
    .filter((entry): entry is { occasion: T; appointment: OccasionOccurrence } =>
      entry.appointment !== null && entry.appointment.date > today && entry.appointment.date <= week)
    .sort((left, right) => left.appointment.date.localeCompare(right.appointment.date) || byTimeThenName(left, right))
    .map(({ occasion, appointment }) => ({
      occasion,
      appointment,
      when: fmt(appointment.date, { weekday: 'short', day: 'numeric' }).toUpperCase(),
      end: appointment.startTime ?? null,
      now: false,
      opens: isSeasonLong(occasion),
    }));
  return {
    today: todayRows.slice(0, 4),
    todayMore: Math.max(0, todayRows.length - 4),
    coming: coming.slice(0, 3),
    comingMore: Math.max(0, coming.length - 3),
    total: current.length,
  };
}

/** The status line of an "Open all season" row. */
export function seasonStatus(occasion: OccasionSchedule, now: Date): { text: string; open: boolean; sort: string } {
  const today = berlinClock(now).date;
  const todays = appointmentOn(occasion, today, now);
  if (todays) {
    const hours = appointmentHours(todays);
    return { text: hours ? `Open today ${hours}` : 'Open today', open: true, sort: `0${String(minutesOf(todays.startTime)).padStart(4, '0')}` };
  }
  const next = nextAppointment(occasion, now);
  if (!next) return { text: 'Check source for dates', open: false, sort: '9' };
  const day = fmt(next.date, { weekday: 'short', day: 'numeric', month: 'short' });
  return {
    text: occasion.startDate > today ? `Opens ${day}` : `Next open ${day}`,
    open: false,
    sort: `1${next.date}${String(minutesOf(next.startTime)).padStart(4, '0')}`,
  };
}

/** "Sat 28 Nov", "Tomorrow", "in 7 days" for a day heading on the reader's clock. */
export function relativeDay(date: string, now: Date): string {
  const today = berlinClock(now).date;
  const days = Math.round((utc(date).getTime() - utc(today).getTime()) / 86_400_000);
  if (days === 0) return 'Today';
  if (days === 1) return 'Tomorrow';
  return `in ${days} days`;
}

export function dayHeading(date: string): string {
  return fmt(date, { weekday: 'short', day: 'numeric', month: 'short' });
}

/** Dates for a search title: absolute, with the year. */
export function titleDates({ startDate, endDate }: Pick<OccasionSummary, 'startDate' | 'endDate'>): string {
  const day = { day: 'numeric', month: 'short' } as const;
  if (startDate === endDate) return fmt(startDate, { weekday: 'short', ...day, year: 'numeric' }).replace(',', '');
  if (startDate.slice(0, 4) === endDate.slice(0, 4)) {
    return `${fmt(startDate, day)} – ${fmt(endDate, { ...day, year: 'numeric' })}`;
  }
  return `${fmt(startDate, { ...day, year: 'numeric' })} – ${fmt(endDate, { ...day, year: 'numeric' })}`;
}

export function searchTitle(occasion: OccasionSummary): string {
  const base = `${occasion.name} · ${titleDates(occasion)}`;
  const place = occasion.area === 'region' && occasion.place?.municipality ? occasion.place.municipality : 'Hannover';
  const withPlace = `${base} · ${place}`;
  return occasion.name.includes(place) || withPlace.length > 65 ? base : withPlace;
}

/** Meta description from absolute facts only: snippets are cached for weeks. */
export function searchDescription(occasion: OccasionSummary, about: string | null): string {
  const long = { day: 'numeric', month: 'long', year: 'numeric' } as const;
  const occurrences = occasion.scheduleConfidence === 'continuous' || occasion.scheduleConfidence === 'discrete'
    ? occasion.occurrences ?? [] : [];
  const hours = new Set(occurrences.map(appointmentHours));
  const single = occasion.startDate === occasion.endDate;
  let when: string;
  if (single) {
    const time = occurrences[0] ? appointmentHours(occurrences[0]) : null;
    when = fmt(occasion.startDate, { weekday: 'long', ...long }).replace(',', '') + (time ? `, ${time}` : '');
  } else {
    const range = occasion.startDate.slice(0, 4) === occasion.endDate.slice(0, 4)
      ? `${fmt(occasion.startDate, { day: 'numeric', month: 'long' })} – ${fmt(occasion.endDate, long)}`
      : `${fmt(occasion.startDate, long)} – ${fmt(occasion.endDate, long)}`;
    const daily = occasion.scheduleConfidence === 'continuous' && hours.size === 1 && !hours.has(null) &&
      occurrences.length > 1 && addDays(occasion.startDate, occurrences.length - 1) === occasion.endDate;
    when = daily ? `Daily ${[...hours][0]}, ${range}`
      : occasion.scheduleConfidence === 'discrete'
        ? `Selected dates from ${fmt(occasion.startDate, long)} to ${fmt(occasion.endDate, long)}`
        : range;
  }
  const status = occasion.sourceStatus === 'cancelled' ? 'Cancelled: '
    : occasion.sourceStatus === 'postponed' ? 'Postponed: ' : '';
  const place = occasion.place
    ? [occasion.place.venue, occasion.place.street, `${occasion.place.postalCode} ${occasion.place.locality}`].filter(Boolean).join(', ')
    : occasion.location;
  const admission = occasion.admission ?? [];
  const free = admission.length === 1 && admission[0].price === 'free' && !admission[0].label && !admission[0].isFrom;
  const tail = about ?? `${single ? 'Date' : 'Dates'}, opening times and address from the official listing.`;
  return `${status}${when} at ${place}.${free ? ' Free entry.' : ''} ${tail}`;
}

export function spanText(occasion: Pick<OccasionSummary, 'startDate' | 'endDate'>): string | null {
  return occasion.startDate === occasion.endDate ? null : sheetDateLine(occasion);
}

export interface IndexWindow { from: string; to: string }

/**
 * The v2 index: season-long occasions in one list, dated ones grouped by the
 * day of their first appointment in the window, each occasion once.
 */
export function indexV2<T extends Named>(occasions: readonly T[], now: Date, window?: IndexWindow) {
  const today = berlinClock(now).date;
  const from = window && window.from > today ? window.from : today;
  const to = window?.to ?? addDays(today, OCCASION_HORIZON_DAYS);
  const firstIn = (occasion: T) => {
    for (let date = from; date <= to; date = addDays(date, 1)) {
      const appointment = appointmentOn(occasion, date, now);
      if (appointment) return { ...appointment, date };
    }
    return null;
  };
  const season: Array<{ occasion: T; appointment: OccasionOccurrence; status: string; open: boolean }> = [];
  const days = new Map<string, Array<{ occasion: T; appointment: OccasionOccurrence }>>();
  const check: T[] = [];
  const off: T[] = [];
  for (const occasion of occasions) {
    if (!occasionIsCurrent(occasion, now) && occasion.sourceStatus !== 'cancelled' && occasion.sourceStatus !== 'postponed') continue;
    if (occasion.sourceStatus === 'cancelled' || occasion.sourceStatus === 'postponed') {
      if (!window && occasion.endDate >= today) off.push(occasion);
      continue;
    }
    const appointment = firstIn(occasion);
    if (!appointment) {
      if (!window && !nextAppointment(occasion, now) && occasion.startDate <= to) check.push(occasion);
      continue;
    }
    if (isSeasonLong(occasion)) {
      const hours = appointmentHours(appointment);
      const status = appointment.date === today
        ? (hours ? `Open today ${hours}` : 'Open today')
        : window
          ? `${dayHeading(appointment.date)}${hours ? ` · ${hours}` : ''}`
          : `${occasion.startDate > today ? 'Opens' : 'Next open'} ${dayHeading(appointment.date)}`;
      season.push({ occasion, appointment, status, open: appointment.date === today });
    } else {
      const list = days.get(appointment.date) ?? [];
      list.push({ occasion, appointment });
      days.set(appointment.date, list);
    }
  }
  season.sort((left, right) => left.appointment.date.localeCompare(right.appointment.date) || byTimeThenName(left, right));
  return {
    season,
    days: [...days].sort(([left], [right]) => left.localeCompare(right))
      .map(([date, entries]) => ({ date, entries: entries.sort(byTimeThenName) })),
    check,
    off,
  };
}
