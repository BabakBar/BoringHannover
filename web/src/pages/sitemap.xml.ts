import type { APIRoute } from 'astro';

export const prerender = true;

const routes = ['/', '/impressum/', '/datenschutz/'];

function escapeXml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

export const GET: APIRoute = ({ site }) => {
  // Sitemaps ideally contain absolute URLs.
  // For local/dev builds (no `site` configured), fall back to localhost.
  const base = (site?.toString() ?? 'http://localhost:4321').replace(/\/$/, '');

  const urlset = routes
    .map((path) => {
      const loc = new URL(path, base).toString();
      return `  <url><loc>${escapeXml(loc)}</loc></url>`;
    })
    .join('\n');

  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
    `${urlset}\n` +
    `</urlset>\n`;

  return new Response(xml, {
    headers: {
      'Content-Type': 'application/xml; charset=utf-8'
    }
  });
};
