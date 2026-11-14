import type { APIRoute } from 'astro';
import { loadEventData } from '../data/loader';
import { addDays, berlinClock } from '../utils/occasionStatus';

export const prerender = true;

function berlinMidnight(date: string): number {
  const utc = new Date(`${date}T00:00:00Z`);
  // Berlin's modern DST transitions occur after midnight; UTC midnight is
  // still on the same local date and carries that midnight's offset.
  return utc.getTime() - berlinClock(utc).minutes * 60000;
}

export const GET: APIRoute = () => new Response(`export default ${JSON.stringify(Object.fromEntries(
  loadEventData().occasions.map(occasion => [occasion.slug, {
    endedAt: berlinMidnight(addDays(occasion.endDate, 1)),
    expiresAt: berlinMidnight(addDays(occasion.endDate, 8)),
  }]),
))};`, { headers: { 'Content-Type': 'application/javascript' } });
