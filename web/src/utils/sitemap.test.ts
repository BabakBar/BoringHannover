import { describe, expect, test } from 'bun:test';
import { buildSitemap, toLastmod } from './sitemap';

describe('toLastmod', () => {
  test('accepts a real ISO timestamp from the backend', () => {
    expect(toLastmod('2026-08-14T09:01:49+02:00')).toBe(
      '2026-08-14T07:01:49.000Z',
    );
  });

  test('omits lastmod when the backend has not written the ISO field', () => {
    expect(toLastmod(undefined)).toBeUndefined();
    expect(toLastmod(null)).toBeUndefined();
    expect(toLastmod('')).toBeUndefined();
  });

  test('omits lastmod for an unparseable value', () => {
    expect(toLastmod('not a date')).toBeUndefined();
  });

  test('rejects the display timestamp, which Date misreads as year 2001', () => {
    // Regression: meta.updatedAt looks date-ish and silently parses to 2001.
    expect(new Date('Tue 28 Jul 11:01').getUTCFullYear()).toBe(2001);
    expect(toLastmod('Tue 28 Jul 11:01')).toBeUndefined();
  });

  test('rejects loose formats that Date accepts but the backend never emits', () => {
    // Each of these parses fine, so Date alone is not a sufficient gate.
    expect(Number.isNaN(new Date('Aug 14 2026').getTime())).toBe(false);
    expect(Number.isNaN(new Date('2026').getTime())).toBe(false);

    expect(toLastmod('Aug 14 2026')).toBeUndefined();
    expect(toLastmod('2026')).toBeUndefined();
    expect(toLastmod('2026-08-14')).toBeUndefined();
    expect(toLastmod('2026-08-14T09:01:49')).toBeUndefined(); // no offset
  });

  test('rejects a calendar date that does not exist', () => {
    // Date rolls this forward to 2026-03-03 rather than failing.
    expect(new Date('2026-02-31T00:00:00Z').toISOString()).toBe(
      '2026-03-03T00:00:00.000Z',
    );
    expect(toLastmod('2026-02-31T00:00:00Z')).toBeUndefined();
    expect(toLastmod('2026-13-01T00:00:00Z')).toBeUndefined();
  });

  test('rejects out-of-range time components', () => {
    expect(toLastmod('2026-08-14T25:00:00Z')).toBeUndefined();
    expect(toLastmod('2026-08-14T09:61:00Z')).toBeUndefined();
  });

  test('accepts the exact shapes the backend emits', () => {
    // datetime.now(BERLIN_TZ).isoformat() -- microseconds plus offset.
    expect(toLastmod('2026-08-15T00:26:55.091414+02:00')).toBe(
      '2026-08-14T22:26:55.091Z',
    );
    // Same instant expressed as UTC.
    expect(toLastmod('2026-08-14T22:26:55Z')).toBe('2026-08-14T22:26:55.000Z');
    // Leap day must still be accepted.
    expect(toLastmod('2028-02-29T12:00:00+02:00')).toBe(
      '2028-02-29T10:00:00.000Z',
    );
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

  test('omits every lastmod when the timestamp is unavailable', () => {
    const lastmod = toLastmod(undefined);
    const xml = buildSitemap(
      [
        { path: '/', lastmod },
        { path: '/special/', lastmod },
      ],
      site,
    );

    expect(xml).not.toContain('<lastmod>');
    expect(xml).toContain('<url><loc>https://boringhannover.de/</loc></url>');
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
