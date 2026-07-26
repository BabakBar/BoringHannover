import type { OccasionSummary } from '../data/types';

export const LANDING_OCCASION_LIMIT = 2;

export function selectLandingOccasions(
  occasions: ReadonlyArray<OccasionSummary>,
): OccasionSummary[] {
  return occasions.slice(0, LANDING_OCCASION_LIMIT);
}
