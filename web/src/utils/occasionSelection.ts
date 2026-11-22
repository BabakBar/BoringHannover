import type { OccasionOccurrence, OccasionSummary } from '../data/types';
import { isSeasonLong } from './occasionSheet';
import {
  OCCASION_HORIZON_DAYS,
  addDays,
  appointmentOn,
  berlinClock,
  nextAppointment,
  occasionIsCurrent,
  type OccasionSchedule,
} from './occasionStatus';

// The homepage board (#114 §5): what is on today, then what starts or
// happens in the next seven days. The build selects once with `live: false`
// (no time-of-day labels, which a static page cannot keep true); the page
// script reselects on the reader's clock.

type BoardOccasion = OccasionSchedule & Pick<OccasionSummary, 'name'>;

export interface BoardRow<T extends BoardOccasion> {
  occasion: T;
  appointment: OccasionOccurrence;
  /** Left column: On now, From 14:00, 14:00, Today, or "Sun 22" coming up. */
  when: string;
  /** Right column: the confirmed end today, the start time coming up. */
  end: string | null;
  now: boolean;
  /** A season-long occasion opening in the coming week. */
  opens: boolean;
}

export interface Board<T extends BoardOccasion> {
  today: BoardRow<T>[];
  todayMore: number;
  coming: BoardRow<T>[];
  /** Confirmed within 30 days: the index's "N occasions in the next 30 days". */
  total: number;
}

const TODAY_LIMIT = 4;
const COMING_LIMIT = 3;

const comingFormat = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', timeZone: 'UTC' });

function minutesOf(time: string | null | undefined): number {
  if (!time) return 24 * 60;
  const [hour, minute] = time.split(':').map(Number);
  return hour * 60 + minute;
}

function byTimeThenName<T extends BoardOccasion>(left: BoardRow<T>, right: BoardRow<T>) {
  return minutesOf(left.appointment.startTime) - minutesOf(right.appointment.startTime) ||
    left.occasion.name.localeCompare(right.occasion.name, 'de');
}

const dayLabel = (date: string) => comingFormat.format(new Date(`${date}T00:00:00Z`));

function todayLabel({ date, startTime, endTime }: OccasionOccurrence, minutes: number, live: boolean) {
  if (!live) return { when: startTime ?? dayLabel(date), now: false };
  if (!startTime) return { when: 'Today', now: false };
  const started = minutes >= minutesOf(startTime);
  // A start-only time is not an open interval: it never earns On now.
  if (started && endTime) return { when: 'On now', now: true };
  return { when: started ? `From ${startTime}` : startTime, now: false };
}

export function boardSelection<T extends BoardOccasion>(
  occasions: readonly T[],
  now: Date,
  { live = true } = {},
): Board<T> {
  const { date: today, minutes } = berlinClock(now);
  const horizon = addDays(today, OCCASION_HORIZON_DAYS);
  const week = addDays(today, 7);
  const current = occasions
    .filter(occasion => occasion.sourceStatus !== 'cancelled' && occasion.sourceStatus !== 'postponed' &&
      occasionIsCurrent(occasion, now))
    .map(occasion => ({ occasion, next: nextAppointment(occasion, now) }))
    .filter(({ next }) => next !== null && next.date <= horizon);

  const todayRows: BoardRow<T>[] = [];
  const coming: BoardRow<T>[] = [];
  for (const { occasion, next } of current) {
    // An unparsed run confirms its start date, which appointmentOn does not know.
    const appointment = appointmentOn(occasion, today, now) ?? (next!.date === today ? next : null);
    if (appointment) {
      const { when, now: on } = todayLabel(appointment, minutes, live);
      todayRows.push({ occasion, appointment, when, end: appointment.endTime ? `–${appointment.endTime}` : null, now: on, opens: false });
      continue;
    }
    const season = isSeasonLong(occasion);
    if (next!.date > week || (season && occasion.startDate <= today)) continue;
    coming.push({
      occasion,
      appointment: next!,
      when: dayLabel(next!.date),
      end: next!.startTime ?? null,
      now: false,
      opens: season,
    });
  }

  todayRows.sort((left, right) =>
    Number(isSeasonLong(left.occasion)) - Number(isSeasonLong(right.occasion)) || byTimeThenName(left, right));
  coming.sort((left, right) => left.appointment.date.localeCompare(right.appointment.date) || byTimeThenName(left, right));
  return {
    today: todayRows.slice(0, TODAY_LIMIT),
    todayMore: Math.max(0, todayRows.length - TODAY_LIMIT),
    coming: coming.slice(0, COMING_LIMIT),
    total: current.length,
  };
}
