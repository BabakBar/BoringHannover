import type { APIRoute } from 'astro';
import { loadEventData } from '../data/loader';
import { buildSitemap, toLastmod, type SitemapRoute } from '../utils/sitemap';

export const prerender = true;

const eventData = loadEventData();

// Only the pages that genuinely change per scrape carry a lastmod, and it comes
// from the backend's real timestamp. The legal pages never get one.
const dataUpdatedAt = toLastmod(eventData.meta.updatedAtISO);

const routes: SitemapRoute[] = [
  { path: '/', lastmod: dataUpdatedAt },
  { path: '/special/', lastmod: dataUpdatedAt },
  ...eventData.occasions.map(occasion => ({
    path: `/special/${occasion.slug}/`,
    lastmod: dataUpdatedAt,
  })),
  { path: '/impressum/' },
  { path: '/datenschutz/' },
];

export const GET: APIRoute = ({ site }) =>
  new Response(buildSitemap(routes, site?.toString()), {
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
    },
  });
