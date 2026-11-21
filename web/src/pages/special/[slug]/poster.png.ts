import type { APIRoute } from 'astro';
import { join } from 'node:path';
import { Resvg } from '@resvg/resvg-js';
import { loadEventData } from '../../../data/loader';
import type { OccasionSummary } from '../../../data/types';
import { posterSvg } from '../../../utils/poster';
import { OCCASION_RETENTION_DAYS, addDays, berlinClock } from '../../../utils/occasionStatus';

export const prerender = true;

const fonts = ['space-mono-latin-400.ttf', 'space-mono-latin-700.ttf']
  .map(file => join(process.cwd(), 'src/assets/poster-fonts', file));

export function getStaticPaths() {
  const today = berlinClock(new Date()).date;
  return loadEventData().occasions
    .filter(occasion => today <= addDays(occasion.endDate, OCCASION_RETENTION_DAYS))
    .map(occasion => ({ params: { slug: occasion.slug }, props: { occasion } }));
}

export const GET: APIRoute = ({ props }) => {
  const svg = posterSvg((props as { occasion: OccasionSummary }).occasion);
  const png = new Resvg(svg, {
    font: { fontFiles: fonts, loadSystemFonts: false, defaultFontFamily: 'Space Mono' },
  }).render().asPng();
  return new Response(png, { headers: { 'Content-Type': 'image/png' } });
};
