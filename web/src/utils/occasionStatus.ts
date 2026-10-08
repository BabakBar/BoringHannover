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
  | 'running';

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
  if (today > schedule.endDate) return label('ended');

  const occurrences = schedule.occurrences ?? [];
  const remaining = occurrences.filter(
    (occurrence) =>
      occurrence.date > today ||
      (occurrence.date === today &&
        !(occurrence.endTime && minutes >= minutesOf(occurrence.endTime))),
  );
  const next = remaining[0];
  if (!next) {
    // The final confirmed appointment is over. A list that stops earlier was
    // cut at the export horizon, so only the envelope remains known.
    if (occurrences.length && occurrences.at(-1)!.date >= schedule.endDate) {
      return label('ended');
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
