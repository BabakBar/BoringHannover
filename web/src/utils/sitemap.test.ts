import { describe, expect, test } from 'bun:test';
import { buildSitemap } from './sitemap';

describe('buildSitemap', () => {
  const site = 'https://boringhannover.de';

  test('emits absolute URLs with lastmod only where supplied', () => {
    const xml = buildSitemap(
      [
        { path: '/', lastmod: '2026-08-14T07:01:49.000Z' },
        { path: '/impressum/' },
      ],
      site,
    );

    expect(xml).toContain(
      '<url><loc>https://boringhannover.de/</loc>' +
        '<lastmod>2026-08-14T07:01:49.000Z</lastmod></url>',
    );
    expect(xml).toContain(
      '<url><loc>https://boringhannover.de/impressum/</loc></url>',
    );
  });

  test('keeps trailing-slash URLs, matching the canonical tags', () => {
    const xml = buildSitemap([{ path: '/special/fahrmannsfest-2026/' }], site);
    expect(xml).toContain(
      'https://boringhannover.de/special/fahrmannsfest-2026/',
    );
  });

  test('tolerates a trailing slash on the configured site', () => {
    expect(buildSitemap([{ path: '/' }], 'https://boringhannover.de/')).toContain(
      '<loc>https://boringhannover.de/</loc>',
    );
  });

  test('escapes XML-significant characters in URLs', () => {
    const xml = buildSitemap([{ path: '/special/rock&roll/' }], site);
    expect(xml).toContain('&amp;');
    expect(xml).not.toMatch(/rock&roll/);
  });
});
