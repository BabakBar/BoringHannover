import type { OccasionOccurrence, OccasionSummary } from '../data/types';
import { appointmentHours, entryPrice, isSeasonLong, sheetDateLine } from './occasionSheet';
import {
  OCCASION_HORIZON_DAYS,
  addDays,
  appointmentOn,
  berlinClock,
  nextAppointment,
  occasionHasEnded,
  type OccasionSchedule,
} from './occasionStatus';

// The /special/ index (#54, #114 §4): season-long occasions in one list, the
// rest under the day of their first confirmed appointment, each occasion once.
// The build lays it out once; the page script redoes it on the reader's clock
// because a static page is served for days.

export type IndexOccasion = OccasionSchedule & Pick<OccasionSummary, 'name'>;

export interface IndexEntry<T extends IndexOccasion> {
  occasion: T;
  /** What places it; null under Check dates and Cancelled or postponed. */
  appointment: OccasionOccurrence | null;
  /** The row's first line: status, hours or dates. */
  when: string;
  /** Open today: the season row's status is emphasised. */
  open: boolean;
}

export interface IndexLayout<T extends IndexOccasion> {
  season: IndexEntry<T>[];
  days: Array<{ date: string; entries: IndexEntry<T>[] }>;
  check: IndexEntry<T>[];
  off: IndexEntry<T>[];
}

export interface IndexWindow {
  startDate: string;
  endDate: string;
}

const dayFormat = new Intl.DateTimeFormat('en-GB', {
  weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC',
});

/** "Sat 28 Nov": absolute, so build-time HTML stays true. */
export function dayHeading(date: string): string {
  return dayFormat.format(new Date(`${date}T00:00:00Z`));
}

/** The script's tag beside a day heading, on the reader's clock. */
export function relativeDay(date: string, now: Date): string {
  const days = Math.round(
    (Date.parse(`${date}T00:00:00Z`) - Date.parse(`${berlinClock(now).date}T00:00:00Z`)) / 86_400_000,
  );
  return days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : `in ${days} days`;
}

function startMinutes({ startTime }: OccasionOccurrence): number {
  if (!startTime) return 24 * 60;
  const [hour, minute] = startTime.split(':').map(Number);
  return hour * 60 + minute;
}

function byName<T extends IndexOccasion>(left: IndexEntry<T>, right: IndexEntry<T>) {
  return left.occasion.name.localeCompare(right.occasion.name, 'de');
}

function byAppointment<T extends IndexOccasion>(left: IndexEntry<T>, right: IndexEntry<T>) {
  return left.appointment!.date.localeCompare(right.appointment!.date) ||
    startMinutes(left.appointment!) - startMinutes(right.appointment!) ||
    byName(left, right);
}

/** Where the source's dates are all a row can say. */
function runText(occasion: IndexOccasion): string {
  const run = sheetDateLine(occasion);
  return occasion.scheduleConfidence === 'discrete' ? `Selected dates · ${run}` : run;
}

/**
 * The first confirmed appointment in the window. A continuous or sparse
 * schedule is read day by day; an unparsed one confirms only its start date,
 * which `nextAppointment` knows and `appointmentOn` does not.
 */
function firstAppointment(occasion: IndexOccasion, now: Date, from: string, to: string) {
  for (let date = from; date <= to; date = addDays(date, 1)) {
    const appointment = appointmentOn(occasion, date, now);
    if (appointment) return appointment;
  }
  const next = nextAppointment(occasion, now);
  return next && next.date >= from && next.date <= to ? next : null;
}

/**
 * All dates (no window) runs through the inclusive 30-day horizon and adds
 * Check dates (no confirmed date ahead) and Cancelled or postponed. A week
 * window shows only what opens in it. Ended occasions are left out.
 */
export function occasionIndex<T extends IndexOccasion>(
  occasions: readonly T[],
  now: Date,
  window?: IndexWindow,
): IndexLayout<T> {
  const today = berlinClock(now).date;
  const from = window && window.startDate > today ? window.startDate : today;
  const to = window?.endDate ?? addDays(today, OCCASION_HORIZON_DAYS);
  const layout: IndexLayout<T> = { season: [], days: [], check: [], off: [] };
  const days = new Map<string, IndexEntry<T>[]>();

  for (const occasion of occasions) {
    if (occasionHasEnded(occasion, now)) continue;
    if (occasion.sourceStatus === 'cancelled' || occasion.sourceStatus === 'postponed') {
      const status = occasion.sourceStatus === 'cancelled' ? 'Cancelled' : 'Postponed';
      if (!window) layout.off.push({ occasion, appointment: null, when: `${status} · ${runText(occasion)}`, open: false });
      continue;
    }
    const appointment = firstAppointment(occasion, now, from, to);
    if (!appointment) {
      if (!window && !nextAppointment(occasion, now)) {
        layout.check.push({ occasion, appointment, when: runText(occasion), open: false });
      }
      continue;
    }
    const hours = appointmentHours(appointment);
    if (isSeasonLong(occasion)) {
      const open = appointment.date === today;
      const day = dayHeading(appointment.date);
      const when = open ? (hours ? `Open today ${hours}` : 'Open today')
        : window ? (hours ? `${day} · ${hours}` : day)
        : `${occasion.startDate > today ? 'Opens' : 'Next open'} ${day}`;
      layout.season.push({ occasion, appointment, when, open });
    } else {
      const entries = days.get(appointment.date) ?? [];
      entries.push({ occasion, appointment, when: hours ?? '', open: false });
      days.set(appointment.date, entries);
    }
  }

  layout.season.sort(byAppointment);
  layout.days = [...days.keys()].sort().map(date => ({ date, entries: days.get(date)!.sort(byAppointment) }));
  for (const list of [layout.check, layout.off]) {
    list.sort((left, right) => left.occasion.startDate.localeCompare(right.occasion.startDate) || byName(left, right));
  }
  return layout;
}

/** What the index's day view at `/special/#day-<date>` lists, so links to it can state it. */
export function dayViewCount(occasions: readonly IndexOccasion[], now: Date, date: string): number {
  const layout = occasionIndex(occasions, now, { startDate: date, endDate: date });
  return layout.season.length + layout.days.reduce((sum, day) => sum + day.entries.length, 0);
}

export const WEEK_NAMES = ['This week', 'Next week', 'Following week'] as const;

const weekDateFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', timeZone: 'UTC',
});

export function occasionWeeks(today: string) {
  const weekday = new Date(`${today}T00:00:00Z`).getUTCDay();
  const monday = addDays(today, -((weekday + 6) % 7));
  return WEEK_NAMES.map((name, offset) => {
    const startDate = addDays(monday, offset * 7);
    const endDate = addDays(startDate, 6);
    const dates = weekDateFormat.formatRange(
      new Date(`${startDate}T00:00:00Z`), new Date(`${endDate}T00:00:00Z`),
    ).replace(/\s*–\s*/u, '–');
    return { name, startDate, endDate, dates };
  });
}

export function indexAdmission(occasion: OccasionSummary): string | null {
  const { admission, sourceStatus } = occasion;
  if (!admission?.length || sourceStatus === 'cancelled' || sourceStatus === 'postponed') {
    return null;
  }
  const [first] = admission;
  if (admission.length !== 1 || first.label) return 'Check entry details';
  return first.price === 'free' ? 'Free entry' : `Entry ${entryPrice(first.price, first.isFrom)}`;
}
