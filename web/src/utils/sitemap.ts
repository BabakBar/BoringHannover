export interface SitemapRoute {
  path: string;
  lastmod?: string;
}

function escapeXml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

export function buildSitemap(routes: SitemapRoute[], site?: string): string {
  // Sitemaps need absolute URLs; dev builds have no configured site.
  const base = (site ?? 'http://localhost:4321').replace(/\/$/, '');

  const urlset = routes
    .map(({ path, lastmod }) => {
      const loc = new URL(path, base).toString();
      const lastmodTag = lastmod
        ? `<lastmod>${escapeXml(lastmod)}</lastmod>`
        : '';
      return `  <url><loc>${escapeXml(loc)}</loc>${lastmodTag}</url>`;
    })
    .join('\n');

  return (
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
    `${urlset}\n` +
    `</urlset>\n`
  );
}
