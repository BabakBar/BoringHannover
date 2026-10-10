import { sanitizeUrl } from './sanitize';

const CITY_CALENDAR_HOSTS = new Set(['hannover.de', 'www.hannover.de']);

export interface OccasionSourceLink {
  url: string;
  label: string;
}

/**
 * An occasion's source link, labelled from its parsed host (#60).
 *
 * hannover.de is the city's event calendar: a listing about the occasion,
 * not the organiser's own site. Every other occasion source is a first-party
 * adapter written against an organiser's or venue's site. Unsafe or
 * unparseable URLs get no link at all.
 */
export function occasionSourceLink(url?: string): OccasionSourceLink | null {
  const safeUrl = sanitizeUrl(url);
  if (safeUrl === '#') return null;
  let host: string;
  try {
    host = new URL(safeUrl).hostname;
  } catch {
    return null;
  }
  return {
    url: safeUrl,
    label: CITY_CALENDAR_HOSTS.has(host)
      ? 'Listing on hannover.de'
      : 'Official website',
  };
}
