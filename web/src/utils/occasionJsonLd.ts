import type { OccasionSummary, SourceStatus } from '../data/types';

const EVENT_STATUS: Record<SourceStatus, string> = {
  scheduled: 'https://schema.org/EventScheduled',
  cancelled: 'https://schema.org/EventCancelled',
  postponed: 'https://schema.org/EventPostponed',
  rescheduled: 'https://schema.org/EventRescheduled',
};

/**
 * schema.org Event for an occasion detail page. eventStatus is asserted only
 * from explicit source status, and dates stay date-only: an envelope is not
 * evidence of opening hours.
 *
 * Sparse (discrete) or unparsed (unknown) schedules get no markup: one Event
 * across their season would claim a continuous event, and separately held
 * dates need their own Event elements, which these pages do not have yet.
 * Continuous schedules and exports without schedule evidence keep it.
 */
export function occasionJsonLd(
  occasion: OccasionSummary,
  { canonicalUrl, officialUrl }: { canonicalUrl?: string; officialUrl?: string | null },
): Record<string, unknown> | undefined {
  if (
    occasion.scheduleConfidence === 'discrete' ||
    occasion.scheduleConfidence === 'unknown'
  ) {
    return undefined;
  }
  return {
    '@context': 'https://schema.org',
    '@type': 'Event',
    name: occasion.name,
    startDate: occasion.startDate,
    endDate: occasion.endDate,
    ...(occasion.sourceStatus === 'rescheduled' && occasion.previousStartDate
      ? { previousStartDate: occasion.previousStartDate }
      : {}),
    description: occasion.description,
    ...(occasion.imageUrl ? { image: occasion.imageUrl } : {}),
    ...(occasion.sourceStatus
      ? { eventStatus: EVENT_STATUS[occasion.sourceStatus] }
      : {}),
    eventAttendanceMode: 'https://schema.org/OfflineEventAttendanceMode',
    location: {
      '@type': 'Place',
      name: occasion.location,
      address: {
        '@type': 'PostalAddress',
        addressLocality: 'Hannover',
        addressCountry: 'DE',
      },
    },
    // url must be the page carrying the markup; the venue's own site is a
    // sameAs reference, not a substitute for it.
    ...(canonicalUrl ? { url: canonicalUrl } : {}),
    ...(officialUrl ? { sameAs: officialUrl } : {}),
  };
}
