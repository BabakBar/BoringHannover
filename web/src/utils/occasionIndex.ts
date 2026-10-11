import type { OccasionOccurrence, OccasionSummary } from '../data/types';
import { appointmentText, sheetDateLine } from './occasionSheet';
import {
  OCCASION_HORIZON_DAYS,
  addDays,
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
  key: 'today' | 'next' | 'following' | 'check' | 'off';
  name: string;
  /** The Berlin dates a dated group covers. */
  dates: string | null;
  entries: IndexEntry<T>[];
}

const DATED_GROUPS = [
  { key: 'today', name: 'Today', from: 0, to: 0 },
  { key: 'next', name: 'Next 7 days', from: 1, to: 7 },
  { key: 'following', name: 'Following 7 days', from: 8, to: OCCASION_HORIZON_DAYS },
] as const;

function byName<T extends IndexOccasion>(left: IndexEntry<T>, right: IndexEntry<T>) {
  return left.occasion.name.localeCompare(right.occasion.name, 'de');
}

/**
 * Disjoint groups in page order: Today, Next 7 days and Following 7 days up
 * to the inclusive horizon, then Check dates (no confirmed date ahead) and
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
    group.entries.sort(
      (left, right) =>
        left.appointment!.date.localeCompare(right.appointment!.date) ||
        (left.appointment!.startTime ?? '24:00').localeCompare(
          right.appointment!.startTime ?? '24:00',
        ) ||
        byName(left, right),
    );
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

/** A row's dates: the appointment that placed it, then the whole run. */
export function indexDates({
  occasion,
  appointment,
}: IndexEntry<IndexOccasion>): { when: string; span: string | null } {
  const run = sheetDateLine(occasion);
  const season =
    occasion.scheduleConfidence === 'discrete' ? `Selected dates · ${run}` : run;
  if (!appointment) return { when: season, span: null };
  return {
    when: appointmentText(appointment),
    span: occasion.startDate === occasion.endDate ? null : season,
  };
}
