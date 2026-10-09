import { describe, expect, test } from 'bun:test';
import { buildSitemap, toLastmod } from './sitemap';

describe('toLastmod', () => {
  test('normalises the shapes the backend emits to UTC', () => {
    // datetime.now(BERLIN_TZ).isoformat(): microseconds plus offset.
    expect(toLastmod('2026-08-15T00:26:55.091414+02:00')).toBe(
      '2026-08-14T22:26:55.091Z',
    );
    expect(toLastmod('2026-08-14T09:01:49+02:00')).toBe(
      '2026-08-14T07:01:49.000Z',
    );
    expect(toLastmod('2026-08-14T22:26:55Z')).toBe('2026-08-14T22:26:55.000Z');
    expect(toLastmod('2028-02-29T12:00:00+02:00')).toBe(
      '2028-02-29T10:00:00.000Z',
    );
  });

  test('omits lastmod rather than guessing', () => {
    for (const raw of [
      undefined,
      null,
      '',
      'not a date',
      'Tue 28 Jul 11:01', // display timestamp; Date reads it as 2001
      'Aug 14 2026',
      '2026',
      '2026-08-14',
      '2026-08-14T09:01:49', // no offset
      '2026-02-31T00:00:00Z', // Date rolls it forward to March
      '2026-13-01T00:00:00Z',
      '2026-08-14T25:00:00Z',
      '2026-08-14T09:61:00Z',
    ]) {
      expect(toLastmod(raw)).toBeUndefined();
    }
  });
});

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
