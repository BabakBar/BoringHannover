import type { OccasionSummary } from '../data/types';

// Labels follow the #59 temporal contract: they read only confirmed facts and
// take the clock as an argument, so the build and the browser share one helper.
export type OccasionSchedule = Pick<
  OccasionSummary,
  'startDate' | 'endDate' | 'occurrences' | 'scheduleConfidence' | 'sourceStatus'
>;

export type OccasionLabelKey =
  | 'cancelled'
  | 'postponed'
  | 'rescheduled'
  | 'ended'
  | 'on_now'
  | 'last_day'
  | 'final_weekend'
  | 'today'
  | 'tomorrow'
  | 'in_days'
  | 'upcoming'
  | 'running'
  | 'check_dates';

export interface OccasionLabel {
  key: OccasionLabelKey;
  text: string;
}

/** Inclusive today..today+14 Berlin horizon, matching EVENT_LOOKAHEAD_DAYS. */
export const OCCASION_HORIZON_DAYS = 14;

const LABEL_TEXT: Record<Exclude<OccasionLabelKey, 'in_days'>, string> = {
  cancelled: 'Cancelled',
  postponed: 'Postponed',
  rescheduled: 'Rescheduled',
  ended: 'Ended',
  on_now: 'On now',
  last_day: 'Last day',
  final_weekend: 'Final weekend',
  today: 'Today',
  tomorrow: 'Tomorrow',
  upcoming: 'Coming soon',
  running: 'Running',
  check_dates: 'Check dates',
};

const berlinFormat = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/Berlin',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

/** Berlin calendar date (YYYY-MM-DD) and minutes since local midnight. */
export function berlinClock(now: Date): { date: string; minutes: number } {
  const parts = Object.fromEntries(
    berlinFormat.formatToParts(now).map((part) => [part.type, part.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    minutes: Number(parts.hour) * 60 + Number(parts.minute),
  };
}

function label(key: Exclude<OccasionLabelKey, 'in_days'>): OccasionLabel {
  return { key, text: LABEL_TEXT[key] };
}

function dayNumber(isoDate: string): number {
  const [year, month, day] = isoDate.split('-').map(Number);
  return Date.UTC(year, month - 1, day) / 86_400_000;
}

function minutesOf(time: string): number {
  const [hour, minute] = time.split(':').map(Number);
  return hour * 60 + minute;
}

function sourceStatusLabel(schedule: OccasionSchedule): OccasionLabel | null {
  const status = schedule.sourceStatus;
  return status && status !== 'scheduled' ? label(status) : null;
}

/** A Saturday or Sunday of a multi-day occasion that began before it and ends within it. */
function isFinalWeekend(schedule: OccasionSchedule, today: string): boolean {
  const day = dayNumber(today);
  const weekday = new Date(day * 86_400_000).getUTCDay();
  if (weekday !== 6 && weekday !== 0) return false;
  const saturday = weekday === 6 ? day : day - 1;
  return (
    dayNumber(schedule.startDate) < saturday &&
    dayNumber(schedule.endDate) <= saturday + 1
  );
}

/** Confirmed occurrences, only for a parsed schedule (the schema agrees). */
function confirmedOccurrences(schedule: OccasionSchedule) {
  const parsed =
    schedule.scheduleConfidence === 'continuous' ||
    schedule.scheduleConfidence === 'discrete';
  return parsed ? schedule.occurrences ?? [] : [];
}

/** Occurrences not yet over at Berlin `today` and `minutes`. */
function remainingOccurrences(
  schedule: OccasionSchedule,
  today: string,
  minutes: number,
) {
  return confirmedOccurrences(schedule).filter(
    (occurrence) =>
      occurrence.date > today ||
      (occurrence.date === today &&
        !(occurrence.endTime && minutes >= minutesOf(occurrence.endTime))),
  );
}

function hasEndedAt(
  schedule: OccasionSchedule,
  today: string,
  minutes: number,
): boolean {
  if (today > schedule.endDate) return true;
  const occurrences = confirmedOccurrences(schedule);
  // The final confirmed appointment is over.
  return (
    occurrences.length > 0 &&
    remainingOccurrences(schedule, today, minutes).length === 0 &&
    occurrences.at(-1)!.date >= schedule.endDate
  );
}

/**
 * Whether the occasion is over at `now`, read from its dates alone. A source
 * status (Rescheduled, Cancelled) wins the label but never keeps an
 * occasion's actions or onward links alive past its end.
 */
export function occasionHasEnded(
  schedule: OccasionSchedule,
  now: Date,
): boolean {
  const { date, minutes } = berlinClock(now);
  return hasEndedAt(schedule, date, minutes);
}

/**
 * Whether the occasion still has dates ahead at `now`: not ended, and a
 * sparse list cut at the export horizon has a date left.
 */
export function occasionIsCurrent(
  schedule: OccasionSchedule,
  now: Date,
): boolean {
  const { date, minutes } = berlinClock(now);
  if (hasEndedAt(schedule, date, minutes)) return false;
  return !(
    schedule.scheduleConfidence === 'discrete' &&
    confirmedOccurrences(schedule).length > 0 &&
    remainingOccurrences(schedule, date, minutes).length === 0
  );
}

/**
 * Build-time label for no-JS HTML. A static page can be served for days, so
 * it never uses the hour or relative days: only source status and whether the
 * occasion has started or ended.
 */
export function staticOccasionLabel(
  schedule: OccasionSchedule,
  now: Date,
): OccasionLabel {
  const status = sourceStatusLabel(schedule);
  if (status) return status;
  const today = berlinClock(now).date;
  if (today > schedule.endDate) return label('ended');
  if (today < schedule.startDate) return label('upcoming');
  return label('running');
}

/**
 * Browser label at `now`. Explicit source status wins. Countdowns need a
 * confirmed occurrence inside the horizon, On now needs confirmed start and
 * end times, and a date envelope alone only says Running.
 */
export function occasionLabel(
  schedule: OccasionSchedule,
  now: Date,
): OccasionLabel {
  const status = sourceStatusLabel(schedule);
  if (status) return status;

  const { date: today, minutes } = berlinClock(now);
  if (hasEndedAt(schedule, today, minutes)) return label('ended');

  // Occurrences count only for a parsed schedule; the schema enforces this
  // too, so a stray list cannot turn into On now.
  const occurrences = confirmedOccurrences(schedule);
  const next = remainingOccurrences(schedule, today, minutes)[0];
  if (!next) {
    // The list was cut at the export horizon and this page is older than
    // the next dates: a sparse schedule cannot claim it is running.
    if (occurrences.length && schedule.scheduleConfidence === 'discrete') {
      return label('check_dates');
    }
    return label(today < schedule.startDate ? 'upcoming' : 'running');
  }

  if (next.date === today) {
    if (
      next.startTime &&
      next.endTime &&
      minutes >= minutesOf(next.startTime) &&
      minutes < minutesOf(next.endTime)
    ) {
      return label('on_now');
    }
    if (schedule.startDate < schedule.endDate && today === schedule.endDate) {
      return label('last_day');
    }
    return label(isFinalWeekend(schedule, today) ? 'final_weekend' : 'today');
  }

  const days = dayNumber(next.date) - dayNumber(today);
  if (days === 1) return label('tomorrow');
  if (days <= OCCASION_HORIZON_DAYS) {
    return { key: 'in_days', text: `In ${days} days` };
  }
  return label('upcoming');
}
