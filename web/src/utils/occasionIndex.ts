import type { OccasionOccurrence, OccasionSummary } from '../data/types';
import { appointmentText, entryPrice, sheetDateLine } from './occasionSheet';
import {
  OCCASION_HORIZON_DAYS,
  addDays,
  appointmentOn,
  berlinClock,
  nextAppointment,
  occasionHasEnded,
  type OccasionSchedule,
} from './occasionStatus';

// The /special/ index (#54): each occasion at most once, grouped by its next
// confirmed appointment at `now`. The build groups once; the page script
// regroups on the reader's clock because a static page is served for days.

export type IndexOccasion = OccasionSchedule & Pick<OccasionSummary, 'name'>;

export interface IndexEntry<T extends IndexOccasion> {
  occasion: T;
  /** What places it in a dated group; null under Check dates and Cancelled. */
  appointment: OccasionOccurrence | null;
}

export interface IndexGroup<T extends IndexOccasion> {
  key: 'week' | 'today' | 'next' | 'following' | 'later' | 'check' | 'off';
  name: string;
  /** The Berlin dates a dated group covers. */
  dates: string | null;
  entries: IndexEntry<T>[];
}

const DATED_GROUPS = [
  { key: 'today', name: 'Today', from: 0, to: 0 },
  { key: 'next', name: 'Next 7 days', from: 1, to: 7 },
  { key: 'following', name: 'Following 7 days', from: 8, to: 14 },
  { key: 'later', name: 'In 15–30 days', from: 15, to: OCCASION_HORIZON_DAYS },
] as const;

function byName<T extends IndexOccasion>(left: IndexEntry<T>, right: IndexEntry<T>) {
  return left.occasion.name.localeCompare(right.occasion.name, 'de');
}

function byAppointment<T extends IndexOccasion>(left: IndexEntry<T>, right: IndexEntry<T>) {
  return left.appointment!.date.localeCompare(right.appointment!.date) ||
    (left.appointment!.startTime ?? '24:00').localeCompare(right.appointment!.startTime ?? '24:00') ||
    byName(left, right);
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

/** Each occasion appears once, at its first still-available opening that week. */
export function occasionIndexForWeek<T extends IndexOccasion>(
  occasions: readonly T[],
  now: Date,
  week: ReturnType<typeof occasionWeeks>[number],
): IndexGroup<T> {
  const today = berlinClock(now).date;
  const dates: string[] = [];
  for (let date = week.startDate < today ? today : week.startDate; date <= week.endDate; date = addDays(date, 1)) {
    dates.push(date);
  }
  const entries: IndexEntry<T>[] = [];
  for (const occasion of occasions) {
    for (const date of dates) {
      const appointment = appointmentOn(occasion, date, now);
      if (!appointment) continue;
      entries.push({ occasion, appointment });
      break;
    }
  }
  return { key: 'week', name: week.name, dates: week.dates, entries: entries.sort(byAppointment) };
}

/**
 * Disjoint dated groups through the inclusive 30-day horizon,
 * then Check dates (no confirmed date ahead) and
 * Cancelled or postponed. Ended occasions and those beyond the horizon are
 * left out. Dated groups sort by appointment, untimed after timed.
 */
export function occasionIndex<T extends IndexOccasion>(
  occasions: readonly T[],
  now: Date,
): IndexGroup<T>[] {
  const today = berlinClock(now).date;
  const dated = DATED_GROUPS.map(({ key, name, from, to }) => ({
    key,
    name,
    dates: sheetDateLine({ startDate: addDays(today, from), endDate: addDays(today, to) }),
    entries: [] as IndexEntry<T>[],
    last: addDays(today, to),
  }));
  const check: IndexGroup<T> = { key: 'check', name: 'Check dates', dates: null, entries: [] };
  const off: IndexGroup<T> = {
    key: 'off',
    name: 'Cancelled or postponed',
    dates: null,
    entries: [],
  };

  for (const occasion of occasions) {
    if (occasionHasEnded(occasion, now)) continue;
    if (occasion.sourceStatus === 'cancelled' || occasion.sourceStatus === 'postponed') {
      off.entries.push({ occasion, appointment: null });
      continue;
    }
    const appointment = nextAppointment(occasion, now);
    if (!appointment) {
      check.entries.push({ occasion, appointment });
      continue;
    }
    dated
      .find((group) => appointment.date <= group.last)
      ?.entries.push({ occasion, appointment });
  }

  for (const group of dated) {
    group.entries.sort(byAppointment);
  }
  for (const group of [check, off]) {
    group.entries.sort(
      (left, right) =>
        left.occasion.startDate.localeCompare(right.occasion.startDate) ||
        byName(left, right),
    );
  }
  return [...dated.map(({ last: _last, ...group }) => group), check, off];
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

/** A row's dates: the appointment that placed it, then the whole run. */
export function indexDates(
  { occasion, appointment }: IndexEntry<IndexOccasion>,
): { when: string; span: string | null } {
  const run = sheetDateLine(occasion);
  const season =
    occasion.scheduleConfidence === 'discrete' ? `Selected dates · ${run}` : run;
  if (!appointment) return { when: season, span: null };
  return {
    when: appointmentText(appointment),
    span: occasion.startDate === occasion.endDate ? null : season,
  };
}
