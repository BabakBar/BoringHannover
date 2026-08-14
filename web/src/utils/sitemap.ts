export interface SitemapRoute {
  path: string;
  lastmod?: string;
}

export function escapeXml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

/**
 * The exact shape Python's `datetime.isoformat()` emits for a timezone-aware
 * datetime, e.g. "2026-08-14T09:01:49.091414+02:00". The offset is required:
 * a naive timestamp is ambiguous, and this value only ever comes from the
 * backend's `meta.updatedAtISO`.
 */
const ISO_TIMESTAMP =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

/**
 * Normalise the backend timestamp into a <lastmod> value.
 *
 * Google discounts lastmod across a whole sitemap once it looks unreliable, so
 * this omits rather than guesses. `new Date()` is far too permissive to be the
 * gate on its own -- it reads the "Sun 26 Jul 16:08" display string as the year
 * 2001, accepts "2026" and "Aug 14 2026", and silently rolls the impossible
 * "2026-02-31" forward to 2026-03-03. So the format is matched exactly and the
 * calendar date is checked for real existence before Date is trusted.
 */
export function toLastmod(raw: string | undefined | null): string | undefined {
  if (!raw) return undefined;

  const match = ISO_TIMESTAMP.exec(raw.trim());
  if (!match) return undefined;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);

  // Reject dates that do not exist; Date would roll them forward instead.
  const probe = new Date(Date.UTC(year, month - 1, day));
  if (probe.getUTCMonth() + 1 !== month || probe.getUTCDate() !== day) {
    return undefined;
  }

  // Catches out-of-range time components, which the pattern alone allows.
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return undefined;

  return parsed.toISOString();
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
