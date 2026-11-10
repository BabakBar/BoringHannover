import type { APIRoute } from 'astro';
import { loadEventData } from '../data/loader';
import { buildSitemap, type SitemapRoute } from '../utils/sitemap';

export const prerender = true;

const eventData = loadEventData();

// meta.updatedAtISO records the export time, not a significant change to each
// page. Even an unrelated Radar update advances it. Omit lastmod until we have
// reliable per-page content-change evidence (#51).
const routes: SitemapRoute[] = [
  { path: '/' },
  { path: '/special/' },
  ...eventData.occasions.map(occasion => ({
    path: `/special/${occasion.slug}/`,
  })),
  { path: '/how-it-works/' },
  { path: '/impressum/' },
  { path: '/datenschutz/' },
];

export const GET: APIRoute = ({ site }) =>
  new Response(buildSitemap(routes, site?.toString()), {
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
    },
  });
