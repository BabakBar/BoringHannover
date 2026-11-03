import {
  addDays,
  berlinClock,
  nextAppointment,
  occasionIsCurrent,
  OCCASION_HORIZON_DAYS,
  type OccasionSchedule,
} from './occasionStatus';

const LANDING_OCCASION_LIMIT = 2;

export function selectLandingOccasions<T extends OccasionSchedule>(
  occasions: readonly T[],
  now: Date,
): T[] {
  const today = berlinClock(now).date;
  const horizon = addDays(today, OCCASION_HORIZON_DAYS);
  return occasions
    .filter((occasion) =>
      occasion.sourceStatus !== 'cancelled' &&
      occasion.sourceStatus !== 'postponed' &&
      occasionIsCurrent(occasion, now) &&
      (nextAppointment(occasion, now)?.date ?? occasion.startDate) <= horizon,
    )
    .slice(0, LANDING_OCCASION_LIMIT);
}
