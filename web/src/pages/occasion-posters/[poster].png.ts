import type { APIRoute } from 'astro';
import { join } from 'node:path';
import { Resvg } from '@resvg/resvg-js';
import { loadEventData } from '../../data/loader';
import type { OccasionSummary } from '../../data/types';
import { OCCASION_RETENTION_DAYS, addDays, berlinClock } from '../../utils/occasionStatus';
import { posterPath, posterSvg } from '../../utils/poster';

// Not under /special/: the nginx guard serves only details and calendar files there.
export const prerender = true;

// resvg cannot read woff2; these are the committed Space Mono woff2, decompressed.
const fontFiles = ['space-mono-latin-400.ttf', 'space-mono-latin-700.ttf']
  .map(file => join(import.meta.env.WEB_PROJECT_ROOT, 'src/assets/poster-fonts', file));

// The detail page's filter: an expired occasion gets neither.
export function getStaticPaths() {
  const today = berlinClock(new Date()).date;
  return loadEventData().occasions
    .filter(occasion => today <= addDays(occasion.endDate, OCCASION_RETENTION_DAYS))
    .map(occasion => ({
      params: { poster: posterPath(occasion).slice('/occasion-posters/'.length, -'.png'.length) },
      props: { occasion },
    }));
}

export const GET: APIRoute = ({ props }) => {
  const svg = posterSvg((props as { occasion: OccasionSummary }).occasion);
  const png = new Resvg(svg, {
    font: { fontFiles, loadSystemFonts: false, defaultFontFamily: 'Space Mono' },
  }).render().asPng();
  return new Response(png, { headers: { 'Content-Type': 'image/png' } });
};
