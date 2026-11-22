import { expect, test } from 'bun:test';
import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { chromium } from 'playwright-core';
import { titleDates } from '../utils/occasionSearch';
import { dayHeading } from '../utils/occasionIndex';
import { sheetDateLine } from '../utils/occasionSheet';
import { addDays, berlinClock } from '../utils/occasionStatus';

const projectRoot = fileURLToPath(new URL('../../', import.meta.url));

test('sitemap omits unsupported modification dates across unrelated Radar updates (#51)', () => {
  const root = mkdtempSync(join(tmpdir(), 'sitemap-build-'));
  const data = join(root, 'data');
  const outDir = join(root, 'dist');
  const site = 'https://boringhannover.de';
  const env = { ...process.env };
  for (const name of Object.keys(env)) {
    if (name.startsWith('WEB_DATA_')) delete env[name];
  }
  const now = new Date();
  const today = berlinClock(now).date;
  const occasion = {
    id: 'sitemap:unchanged',
    slug: 'unchanged-festival',
    name: 'Unchanged festival',
    kind: 'festival',
    startDate: today,
    endDate: addDays(today, 7),
    location: 'Hannover',
    description: 'A city festival.',
    sourceUrl: 'https://example.com/festival',
    status: 'happening_now',
    programmeCount: 0,
    locationCount: 0,
    programmePath: 'occasions/unchanged-festival.json',
    preview: [],
  };
  try {
    mkdirSync(join(data, 'occasions'), { recursive: true });
    // The occasion and its checked time stay unchanged when Radar changes.
    writeFileSync(join(data, occasion.programmePath), JSON.stringify({
      meta: { updatedAt: 'Original occasion check' }, occasion, programme: [],
    }));
    let originalSitemap: string | undefined;
    for (const update of [0, 1]) {
      const updatedAt = `Scrape ${update}`;
      writeFileSync(join(data, 'web_events.json'), JSON.stringify({
        meta: {
          week: 45, year: 2026, updatedAt,
          updatedAtISO: new Date(now.getTime() - (1 - update) * 3600000).toISOString(),
        },
        movies: [],
        concerts: update ? [{
          title: 'New Radar concert', date: '10 Nov', dateISO: today,
          day: 'Tue', time: '20:00', venue: 'Example venue',
        }] : [],
        occasions: [occasion],
      }));
      const result = spawnSync(process.execPath, [
        join(projectRoot, 'node_modules/astro/bin/astro.mjs'),
        'build', '--root', projectRoot, '--outDir', outDir,
      ], {
        cwd: root,
        env: { ...env, SITE: site, WEB_DATA_ROOT: data, WEB_DATA_MODE: 'production' },
        encoding: 'utf8',
        timeout: 30000,
      });
      if (result.error) throw result.error;
      expect(result.status, result.stdout + result.stderr).toBe(0);
      const html = readFileSync(join(outDir, 'index.html'), 'utf8');
      expect(html).toContain(updatedAt);
      expect(html.includes('New Radar concert')).toBe(Boolean(update));
      const detail = readFileSync(join(outDir, 'special', occasion.slug, 'index.html'), 'utf8');
      expect(detail).toContain(`rel="canonical" href="${site}/special/${occasion.slug}/"`);
      expect(detail).toContain('Checked Original occasion check');
      const sitemap = readFileSync(join(outDir, 'sitemap.xml'), 'utf8');
      expect([...sitemap.matchAll(/<loc>(.*?)<\/loc>/g)].map(([, loc]) => loc)).toEqual([
        `${site}/`, `${site}/special/`, `${site}/special/${occasion.slug}/`,
        `${site}/how-it-works/`, `${site}/impressum/`, `${site}/datenschutz/`,
      ]);
      expect(sitemap).not.toContain('<lastmod>');
      if (originalSitemap !== undefined) expect(sitemap).toBe(originalSitemap);
      originalSitemap = sitemap;
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}, 120000);

test('homepage always links to the occasion index, including small and empty inventories', () => {
  const root = mkdtempSync(join(tmpdir(), 'occasion-navigation-'));
  const data = join(root, 'data');
  const outDir = join(root, 'dist');
  mkdirSync(join(data, 'occasions'), { recursive: true });
  const env = { ...process.env };
  for (const name of Object.keys(env)) {
    if (name.startsWith('WEB_DATA_')) delete env[name];
  }
  const meta = { week: 45, year: 2026, updatedAt: 'Navigation fixture', updatedAtISO: new Date().toISOString() };
  const today = berlinClock(new Date()).date;
  const occasions = Array.from({ length: 3 }, (_, index) => ({
    id: `navigation:${index}`,
    slug: `occasion-${index}`,
    name: `Occasion ${index}`,
    kind: 'festival',
    startDate: addDays(today, index + 1),
    endDate: addDays(today, index + 1),
    location: 'Hannover',
    description: 'A city festival.',
    sourceUrl: 'https://example.com/festival',
    status: 'happening_now',
    programmeCount: 0,
    locationCount: 0,
    programmePath: `occasions/occasion-${index}.json`,
    preview: [],
  }));
  const expired = { ...occasions[0], id: 'expired', slug: 'expired', name: 'Expired festival', startDate: addDays(today, -2), endDate: addDays(today, -1), programmePath: 'occasions/expired.json' };
  try {
    for (const occasion of [...occasions, expired]) {
      writeFileSync(join(data, occasion.programmePath), JSON.stringify({ meta, occasion, programme: [] }));
    }
    for (const count of [0, 1, 2, 3]) {
      writeFileSync(join(data, 'web_events.json'), JSON.stringify({
        meta, movies: [], concerts: [], occasions: [expired, ...occasions.slice(0, count)],
      }));
      const result = spawnSync(process.execPath, [
        join(projectRoot, 'node_modules/astro/bin/astro.mjs'),
        'build', '--root', projectRoot, '--outDir', outDir,
      ], {
        cwd: root,
        env: { ...env, WEB_DATA_ROOT: data, WEB_DATA_MODE: 'production' },
        encoding: 'utf8',
        timeout: 30000,
      });
      if (result.error) throw result.error;
      expect(result.status, result.stdout + result.stderr).toBe(0);
      const html = readFileSync(join(outDir, 'index.html'), 'utf8');
      // The board's footer, or a plain link when nothing is current; never both.
      const hidden = (attribute: string) =>
        new RegExp(`<[^>]*${attribute}(?=[\\s>])[^>]*\\shidden(?=[\\s>])`).test(html);
      expect(hidden('data-board'), `${count} occasions`).toBe(count === 0);
      expect(hidden('data-board-fallback'), `${count} occasions`).toBe(count > 0);
      const indexLinks = [...html.matchAll(/<a\b[^>]*href="\/special\/"[^>]*data-umami-event="occasion-index-open"[^>]*>([\s\S]*?)<\/a>/g)]
        .map(([, text]) => text.trim());
      expect(indexLinks).toEqual([`All ${count} City Occasions →`, 'City Occasions']);
      expect(readFileSync(join(outDir, 'special/index.html'), 'utf8')).toContain('City Occasions');
      const rows = [...html.matchAll(/data-board-row="([^"]+)"/g)].map(([, slug]) => slug);
      expect(rows).toEqual(occasions.slice(0, count).map(occasion => occasion.slug));
      expect(html).not.toContain('Expired festival');
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}, 120000);

test('Astro build selects the anchored root and rejects missing production data', () => {
  const root = mkdtempSync(join(tmpdir(), 'handoff-build-'));
  const env = { ...process.env };
  for (const name of [
    'WEB_DATA_ROOT',
    'WEB_DATA_MODE',
    'WEB_DATA_MAX_AGE_DAYS',
    'WEB_EVENTS_PATH',
  ])
    delete env[name];
  const outDir = join(root, 'dist');
  const build = (overrides: Record<string, string> = {}) => {
    const result = spawnSync(
      process.execPath,
      [
        join(projectRoot, 'node_modules/astro/bin/astro.mjs'),
        'build',
        '--root',
        projectRoot,
        '--outDir',
        outDir,
      ],
      {
        cwd: root,
        env: { ...env, ...overrides },
        encoding: 'utf8',
        timeout: 30000,
      },
    );
    if (result.error) throw result.error;
    return { status: result.status, log: result.stdout + result.stderr };
  };
  try {
    mkdirSync(join(root, 'output'));
    writeFileSync(join(root, 'output/web_events.json'), '{decoy:broken}');
    // Fixture mode permits the committed snapshot to age without making this test time-dependent.
    const anchored = build({ WEB_DATA_MODE: 'fixture' });
    expect(anchored.status, anchored.log).toBe(0);
    expect(anchored.log.match(/\[web-data\] \{/g)?.length).toBe(1);
    const html = readFileSync(join(outDir, 'index.html'), 'utf8');
    expect(html).toContain('name="data-revision"');
    expect(html).not.toContain(projectRoot);
    const architecture = readFileSync(join(outDir, 'how-it-works/index.html'), 'utf8');
    expect(/<h1\b[^>]*>\s*How boringhannover\.de is built\s*<\/h1>/.test(architecture)).toBe(true);
    const noScript = architecture.match(/<noscript>([\s\S]*?)<\/noscript>/)?.[1];
    expect(noScript).toContain('What it does');
    expect(noScript).toContain('Why it');
    expect(noScript).toContain('Data update');
    expect(noScript).toContain('manifest last');
    expect(noScript).not.toMatch(/CSV|Markdown/);
    expect(noScript).toContain('JSON web snapshot');
    expect(noScript).toContain('patch and minor');
    expect(noScript).toContain('major updates need review');
    expect(noScript).toContain('Trivy scans the published images');
    expect(/<g\b[^>]*data-edge="commit"[^>]*role="button"[^>]*tabindex="0"/.test(architecture)).toBe(true);
    const missing = join(root, 'missing');
    const rejected = build({
      WEB_DATA_ROOT: missing,
      WEB_DATA_MODE: 'production',
    });
    expect(rejected.status).not.toBe(0);
    expect(rejected.log).toContain(join(missing, 'web_events.json'));
    expect(rejected.log).toContain('cannot read manifest');
    const fixture = join(root, 'fixture');
    mkdirSync(fixture);
    writeFileSync(
      join(fixture, 'web_events.json'),
      JSON.stringify({
        meta: {
          week: 12,
          year: 2026,
          updatedAt: 'Explicit fixture',
          updatedAtISO: new Date().toISOString(),
        },
        movies: [],
        concerts: [],
        occasions: [],
      }),
    );
    const explicit = build({
      WEB_DATA_ROOT: fixture,
      WEB_DATA_MODE: 'production',
    });
    expect(explicit.status).toBe(0);
    expect(readFileSync(join(outDir, 'index.html'), 'utf8')).toContain(
      'Explicit fixture',
    );
    // No occasions: the index says so and points to the digest and the source.
    const emptyIndex = readFileSync(join(outDir, 'special/index.html'), 'utf8');
    const empty = emptyIndex.match(
      /<div[^>]*data-index-empty[^>]*>([\s\S]*?)<\/div>\s*<\/div>/,
    )?.[1];
    expect(empty).toContain('No City Occasions are listed for the next 30 days.');
    expect(empty).toContain('href="/"');
    expect(empty).toContain(
      'href="https://www.hannover.de/Veranstaltungskalender/Feste-Festivals"',
    );
    expect(
      [...emptyIndex.matchAll(/data-index-part="(\w+)"([^>]*)>/g)]
        .map(([, key, attributes]) => [key, / hidden(?=[ >])/.test(attributes)]),
    ).toEqual([['season', true], ['days', true], ['check', true], ['off', true]]);
    expect(emptyIndex).not.toMatch(/<div class="index-empty"[^>]*\shidden/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}, 120000);

test('occasion pages render source status, sparse dates and source hours without JS', () => {
  const root = mkdtempSync(join(tmpdir(), 'occasion-build-'));
  const env = { ...process.env };
  for (const name of ['WEB_DATA_ROOT', 'WEB_DATA_MODE', 'WEB_DATA_MAX_AGE_DAYS'])
    delete env[name];
  const data = join(root, 'data');
  const outDir = join(root, 'dist');
  const start = addDays(berlinClock(new Date()).date, 1);
  const later = addDays(start, 7);
  const occasion = (slug: string, extra: Record<string, unknown>) => ({
    id: `hannover-festivals:${slug}`,
    slug,
    name: slug,
    kind: 'festival',
    startDate: start,
    endDate: addDays(start, 8),
    location: 'Parkbühne',
    description: 'Ein Fest.',
    imageUrl: null,
    sourceUrl: `https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/${slug}`,
    status: 'happening_now',
    programmeCount: 0,
    locationCount: 0,
    programmePath: `occasions/${slug}.json`,
    preview: [],
    ...extra,
  });
  const occasions = [
    occasion('abgesagtes-fest', { sourceStatus: 'cancelled' }),
    occasion('wiesn', {
      scheduleConfidence: 'discrete',
      occurrences: [
        { date: start, startTime: '18:00' },
        { date: later, startTime: '18:00' },
      ],
    }),
    occasion('flohmarkt', {
      scheduleConfidence: 'unknown',
      hoursText: '04.10.2026 bis 18.10.2026 ab 08:00 bis 17:00 Uhr sonntags',
    }),
  ];
  try {
    mkdirSync(join(data, 'occasions'), { recursive: true });
    writeFileSync(
      join(data, 'web_events.json'),
      JSON.stringify({
        meta: {
          week: 41,
          year: 2026,
          updatedAt: 'Fri 09 Oct 11:00',
          updatedAtISO: '2026-10-09T11:00:00+02:00',
        },
        movies: [],
        concerts: [],
        occasions,
      }),
    );
    for (const item of occasions)
      writeFileSync(
        join(data, item.programmePath),
        JSON.stringify({
          meta: { updatedAt: 'Fri 09 Oct 11:00' },
          occasion: item,
          programme: [],
        }),
      );
    const result = spawnSync(
      process.execPath,
      [
        join(projectRoot, 'node_modules/astro/bin/astro.mjs'),
        'build',
        '--root',
        projectRoot,
        '--outDir',
        outDir,
      ],
      {
        cwd: root,
        env: { ...env, WEB_DATA_ROOT: data, WEB_DATA_MODE: 'fixture' },
        encoding: 'utf8',
        timeout: 60000,
      },
    );
    if (result.error) throw result.error;
    expect(result.status, result.stdout + result.stderr).toBe(0);
    const page = (slug: string) =>
      readFileSync(join(outDir, 'special', slug, 'index.html'), 'utf8');

    const cancelled = page('abgesagtes-fest');
    expect(cancelled).toMatch(/data-occasion-status[^>]*>\s*Cancelled\s*</);
    expect(cancelled).toContain('https://schema.org/EventCancelled');
    // Sparse and unparsed schedules get no Event spanning their whole season.
    // (With SITE set, every page also carries site-wide Organization markup.)
    expect(page('wiesn')).not.toContain('"@type":"Event"');
    expect(page('flohmarkt')).not.toContain('"@type":"Event"');
    expect(cancelled).toContain('"@type":"Event"');

    const wiesn = page('wiesn');
    expect(wiesn).toContain('data-occasion-schedule=');
    // Scoped styles add data-astro-cid-* attributes to these elements.
    expect(wiesn).toMatch(
      new RegExp(`<time datetime="${start}T18:00"[^>]*>[^<]*· from 18:00\\s*</time>`),
    );
    expect(wiesn).toMatch(new RegExp(`<time datetime="${later}T18:00"[^>]*>`));

    expect(page('flohmarkt')).toMatch(
      /<p[^>]*lang="de"[^>]*>04\.10\.2026 bis 18\.10\.2026 ab 08:00 bis 17:00 Uhr sonntags<\/p>/,
    );
    expect(page('flohmarkt')).toContain('Read source schedule (German)');
    // The homepage board lists the openings; the cancelled one is left out.
    const home = readFileSync(join(outDir, 'index.html'), 'utf8');
    expect([...home.matchAll(/data-board-row="([^"]+)"/g)].map(([, slug]) => slug)).toEqual(['wiesn', 'flohmarkt']);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}, 120000);

test('occasion pages share owned imagery, truthful source labels and English copy (#60)', () => {
  const root = mkdtempSync(join(tmpdir(), 'occasion-share-'));
  const env = { ...process.env };
  for (const name of ['WEB_DATA_ROOT', 'WEB_DATA_MODE', 'WEB_DATA_MAX_AGE_DAYS'])
    delete env[name];
  const data = join(root, 'data');
  const outDir = join(root, 'dist');
  const today = berlinClock(new Date()).date;
  const occasion = (slug: string, extra: Record<string, unknown>) => ({
    id: `hannover-festivals:${slug}`,
    slug,
    name: slug,
    kind: 'festival',
    startDate: today,
    endDate: today,
    location: 'Tiergarten',
    description: `${slug} at Tiergarten. See the source for details.`,
    sourceUrl: `https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/${slug}`,
    status: 'upcoming',
    programmeCount: 0,
    locationCount: 0,
    programmePath: `occasions/${slug}.json`,
    preview: [],
    ...extra,
  });
  const longDate = (date: string) => new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  }).format(new Date(`${date}T00:00:00Z`)).replace(',', '');
  const hostile = '</script><!--<script>alert(1)</script>';
  const occasions = [
    // Old snapshots still carry a third-party photo.
    occasion('tiergartenfest-hannover', {
      name: 'Tiergartenfest Hannover',
      description: 'Tiergartenfest Hannover at Tiergarten. See the source for details.',
      imageUrl:
        'https://www.hannover.de/var/storage/images/_aliases/full/Tiergartenfest 05.jpg.webp',
    }),
    occasion('lichterfest-neustadt', {
      name: 'Lichterfest in Neustadt a. Rbge.',
      location: 'Liebfrauenkirche',
      description: 'Lichterfest in Neustadt a. Rbge. at Liebfrauenkirche. See the source for details.',
      scheduleConfidence: 'unknown',
      place: {
        venue: 'Liebfrauenkirche',
        street: 'An der Liebfrauenkirche 1',
        postalCode: '31535',
        locality: 'Neustadt am Rübenberge',
        municipality: 'Neustadt am Rübenberge',
      },
    }),
    occasion('maschseefest-2026', {
      name: 'Maschseefest',
      location: 'Around the Maschsee',
      description: "Music, food, family moments and late nights around Hannover's lake.",
      sourceUrl: 'https://www.maschseefest.de/veranstaltungen/',
    }),
    occasion('boeses-fest', {
      name: `Böses ${hostile} Fest`,
      sourceUrl: 'javascript:alert(1)',
    }),
    // Past retention: neither a detail page nor a poster.
    occasion('vorbei', { startDate: addDays(today, -8), endDate: addDays(today, -8) }),
  ];
  try {
    mkdirSync(join(data, 'occasions'), { recursive: true });
    writeFileSync(
      join(data, 'web_events.json'),
      JSON.stringify({
        meta: {
          week: 41,
          year: 2026,
          updatedAt: 'Fri 09 Oct 11:00',
          updatedAtISO: '2026-10-09T11:00:00+02:00',
        },
        movies: [],
        concerts: [],
        occasions,
      }),
    );
    for (const item of occasions)
      writeFileSync(
        join(data, item.programmePath),
        JSON.stringify({
          meta: { updatedAt: 'Fri 09 Oct 11:00' },
          occasion: item,
          programme: [],
        }),
      );
    const result = spawnSync(
      process.execPath,
      [
        join(projectRoot, 'node_modules/astro/bin/astro.mjs'),
        'build',
        '--root',
        projectRoot,
        '--outDir',
        outDir,
      ],
      {
        cwd: root,
        env: {
          ...env,
          SITE: 'https://boringhannover.de',
          WEB_DATA_ROOT: data,
          WEB_DATA_MODE: 'fixture',
        },
        encoding: 'utf8',
        timeout: 60000,
      },
    );
    if (result.error) throw result.error;
    expect(result.status, result.stdout + result.stderr).toBe(0);
    const page = (slug: string) =>
      readFileSync(join(outDir, 'special', slug, 'index.html'), 'utf8');
    const meta = (html: string, key: string) =>
      html.match(new RegExp(`<meta (?:name|property)="${key}" content="([^"]*)"`))?.[1];
    // Every JSON-LD block must stay valid JSON; returns the Event node.
    const eventJsonLd = (html: string) => {
      const blocks = [
        ...html.matchAll(/<script type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/g),
      ].map((match) => JSON.parse(match[1]));
      return blocks.find((block) => block['@type'] === 'Event');
    };

    const tiergarten = page('tiergartenfest-hannover');
    // One owned 1200 × 630 poster per published occasion, shared by its detail page.
    const posters = readdirSync(join(outDir, 'occasion-posters')).sort();
    expect(posters.map(file => file.replace(/-[0-9a-f]{8}\.png$/, ''))).toEqual(
      ['boeses-fest', 'lichterfest-neustadt', 'maschseefest-2026', 'tiergartenfest-hannover'],
    );
    for (const file of posters) {
      const html = page(file.replace(/-[0-9a-f]{8}\.png$/, ''));
      const url = `https://boringhannover.de/occasion-posters/${file}`;
      expect(meta(html, 'og:image'), file).toBe(url);
      expect(meta(html, 'twitter:image'), file).toBe(url);
      expect([meta(html, 'og:image:width'), meta(html, 'og:image:height')], file).toEqual(['1200', '630']);
      const png = readFileSync(join(outDir, 'occasion-posters', file));
      expect([png.readUInt32BE(16), png.readUInt32BE(20)], file).toEqual([1200, 630]);
    }
    expect(meta(tiergarten, 'og:image:alt')).toBe('Tiergartenfest Hannover: share poster with date and venue');
    expect(existsSync(join(outDir, 'special', 'vorbei'))).toBe(false);
    expect(tiergarten).not.toContain('var/storage/images');
    const tiergartenEvent = eventJsonLd(tiergarten);
    expect(tiergartenEvent).not.toHaveProperty('image');
    expect(tiergartenEvent.location).toEqual({ '@type': 'Place', name: 'Tiergarten' });
    // The exporter's fallback is never shown: search text comes from facts.
    expect(tiergarten).not.toContain('See the source for details.');
    expect(tiergarten).toContain(`<title>Tiergartenfest Hannover · ${titleDates({ startDate: today, endDate: today })}</title>`);
    const tiergartenDescription = `${longDate(today)} at Tiergarten.`;
    for (const key of ['description', 'og:description', 'twitter:description'])
      expect(meta(tiergarten, key)).toBe(tiergartenDescription);
    expect(tiergartenEvent.description).toBe(tiergartenDescription);
    expect(tiergarten).not.toContain('catching up');
    expect(tiergarten).toMatch(/>\s*Listing on hannover\.de\s*</);
    expect(tiergarten).not.toContain('Official Tiergartenfest Hannover website');

    const lichterfest = page('lichterfest-neustadt');
    const lichterfestDescription = `${longDate(today)} at Liebfrauenkirche, An der Liebfrauenkirche 1, 31535 Neustadt am Rübenberge.`;
    for (const key of ['description', 'og:description', 'twitter:description'])
      expect(meta(lichterfest, key)).toBe(lichterfestDescription);
    expect(eventJsonLd(lichterfest)).toBeUndefined();

    const maschsee = page('maschseefest-2026');
    expect(maschsee).toMatch(/>\s*Official website\s*</);
    expect(maschsee).not.toContain('Listing on hannover.de');
    expect(meta(maschsee, 'description')).toBe(
      `${longDate(today)} at Around the Maschsee. Music, food, family moments and late nights around Hannover's lake.`,
    );
    expect(eventJsonLd(maschsee).description).toBe(
      "Music, food, family moments and late nights around Hannover's lake.",
    );

    const hostilePage = page('boeses-fest');
    // Inside a quoted attribute "<" is inert; everywhere else it must be escaped.
    const markup = hostilePage.replace(/="[^"]*"/g, '=""');
    expect(markup).not.toContain('<script>alert(1)');
    expect(markup).not.toContain('<!--<script>');
    expect(markup).toContain('&lt;/script&gt;&lt;!--&lt;script&gt;alert(1)');
    const hostileEvent = eventJsonLd(hostilePage);
    expect(hostileEvent.name).toBe(`Böses ${hostile} Fest`);
    expect(hostileEvent).not.toHaveProperty('sameAs');
    expect(hostilePage).not.toContain('javascript:alert');
    expect(hostilePage).not.toContain('class="occasion-source');
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}, 120000);

test('the occasion sheet puts About before practical facts and works without JS (#54)', () => {
  const root = mkdtempSync(join(tmpdir(), 'occasion-sheet-'));
  const env = { ...process.env };
  for (const name of ['WEB_DATA_ROOT', 'WEB_DATA_MODE', 'WEB_DATA_MAX_AGE_DAYS'])
    delete env[name];
  const data = join(root, 'data');
  const outDir = join(root, 'dist');
  // Dates relative to the Berlin build day keep onward selection current.
  const berlinToday = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Berlin',
  }).format(new Date());
  const day = (offset: number) =>
    new Date(Date.parse(`${berlinToday}T12:00:00Z`) + offset * 86400000)
      .toISOString()
      .slice(0, 10);
  const occasion = (slug: string, extra: Record<string, unknown>) => ({
    id: `hannover-festivals:${slug}`,
    slug,
    name: slug,
    kind: 'festival',
    startDate: day(1),
    endDate: day(1),
    location: 'Parkbühne',
    description: `${slug} at Parkbühne. See the source for details.`,
    sourceUrl: `https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/${slug}`,
    status: 'upcoming',
    programmeCount: 0,
    locationCount: 0,
    programmePath: `occasions/${slug}.json`,
    preview: [],
    ...extra,
  });
  const occasions = [
    occasion('tiergartenfest-hannover', {
      name: 'Tiergartenfest Hannover',
      location: 'Tiergarten',
      description: 'Tiergartenfest Hannover at Tiergarten. See the source for details.',
      scheduleConfidence: 'continuous',
      occurrences: [{ date: day(1), startTime: '13:00', endTime: '18:30' }],
      place: {
        venue: 'Tiergarten',
        street: 'Tiergartenstraße 117',
        postalCode: '30559',
        locality: 'Hannover',
        municipality: 'Hannover',
      },
      area: 'city',
      admission: [
        { label: 'Mit Baumscheibe (für Eichel- und Kastaniensammler*innen)', price: 'free' },
        { label: 'Erwachsene', price: '€3' },
        { label: 'Kinder (bis 14 Jahre)', price: '€2' },
      ],
    }),
    occasion('kunst-kurbis-in-eldagsen', {
      name: 'Kunst & Kürbis in Eldagsen',
      location: 'Eldagser Hoflieferant',
      startDate: day(8),
      endDate: day(8),
      scheduleConfidence: 'continuous',
      occurrences: [{ date: day(8), startTime: '11:00', endTime: '17:00' }],
      place: {
        venue: 'Eldagser Hoflieferant',
        street: 'Lange Straße 142',
        postalCode: '31832',
        locality: 'Springe',
        municipality: 'Springe',
      },
      area: 'region',
      admission: [{ price: 'free' }],
    }),
    occasion('hannover-wies-27n', {
      name: "Hannover Wies'n",
      startDate: day(0),
      endDate: day(29),
      scheduleConfidence: 'discrete',
      occurrences: [
        { date: day(1), startTime: '18:00' },
        { date: day(7), startTime: '18:00' },
      ],
    }),
    occasion('abgesagtes-fest', {
      name: 'Abgesagtes Fest',
      sourceStatus: 'cancelled',
      place: {
        street: 'Bruchmeisterallee 1A',
        postalCode: '30169',
        locality: 'Hannover',
        municipality: 'Hannover',
      },
      area: 'city',
    }),
    // Four one-offs open on Tiergartenfest's day: three fill "Also on".
    occasion('fruehmarkt', {
      name: 'Frühmarkt',
      scheduleConfidence: 'continuous',
      occurrences: [{ date: day(1), startTime: '10:00', endTime: '16:00' }],
    }),
    occasion('adventsbasar', {
      name: 'Adventsbasar',
      scheduleConfidence: 'continuous',
      occurrences: [{ date: day(1), startTime: '14:00', endTime: '20:00' }],
    }),
    occasion('lichterabend', { name: 'Lichterabend' }),
    // Pages can outlive their dates (stale data, ended retention): neither
    // may offer actions, and neither is onward discovery.
    occasion('gestern-vorbei', {
      name: 'Gestern vorbei',
      startDate: day(-2),
      endDate: day(-1),
      place: {
        street: 'Bruchmeisterallee 1A',
        postalCode: '30169',
        locality: 'Hannover',
        municipality: 'Hannover',
      },
      area: 'city',
    }),
    occasion('verlegt-und-vorbei', {
      name: 'Verlegt und vorbei',
      startDate: day(-1),
      endDate: day(-1),
      sourceStatus: 'rescheduled',
      previousStartDate: day(-5),
      scheduleConfidence: 'continuous',
      occurrences: [{ date: day(-1), startTime: '19:00', endTime: '22:00' }],
      place: {
        street: 'Bruchmeisterallee 1A',
        postalCode: '30169',
        locality: 'Hannover',
        municipality: 'Hannover',
      },
      area: 'city',
    }),
  ];
  try {
    mkdirSync(join(data, 'occasions'), { recursive: true });
    writeFileSync(
      join(data, 'web_events.json'),
      JSON.stringify({
        meta: {
          week: 41,
          year: 2026,
          updatedAt: 'Fri 09 Oct 11:00',
          updatedAtISO: `${day(0)}T00:30:00+02:00`,
        },
        movies: [],
        concerts: [],
        occasions,
      }),
    );
    for (const item of occasions)
      writeFileSync(
        join(data, item.programmePath),
        JSON.stringify({
          meta: { updatedAt: 'Fri 09 Oct 11:00' },
          occasion: item,
          programme: [],
        }),
      );
    const result = spawnSync(
      process.execPath,
      [
        join(projectRoot, 'node_modules/astro/bin/astro.mjs'),
        'build',
        '--root',
        projectRoot,
        '--outDir',
        outDir,
      ],
      {
        cwd: root,
        env: {
          ...env,
          SITE: 'https://boringhannover.de',
          WEB_DATA_ROOT: data,
          WEB_DATA_MODE: 'fixture',
        },
        encoding: 'utf8',
        timeout: 60000,
      },
    );
    if (result.error) throw result.error;
    expect(result.status, result.stdout + result.stderr).toBe(0);
    const page = (slug: string) =>
      readFileSync(join(outDir, 'special', slug, 'index.html'), 'utf8');
    // Text content in reading order, without tags or scripts.
    const text = (html: string) =>
      html
        .replace(/<script[\s\S]*?<\/script>/g, ' ')
        .replace(/<[^>]+>/g, ' ')
        .replace(/\s+/g, ' ');
    const before = (html: string, ...markers: string[]) => {
      const positions = markers.map((marker) => html.indexOf(marker));
      expect(positions, markers.join(' < ')).not.toContain(-1);
      expect(positions).toEqual([...positions].sort((a, b) => a - b));
    };

    const tiergarten = page('tiergartenfest-hannover');
    const tiergartenText = text(tiergarten);
    // Name and the date tile, then practical facts, actions and onward links.
    // The exporter's fallback sentence is no About text.
    expect(tiergartenText).not.toContain(' About ');
    expect(tiergartenText).not.toContain('See the source for details.');
    const [weekday, dayNumber, month] = sheetDateLine({ startDate: day(1), endDate: day(1) }).split(' ');
    before(
      text(tiergarten.slice(tiergarten.indexOf('<article'))),
      'Tiergartenfest Hannover',
      `${weekday} ${dayNumber} ${month}`,
      'Coming soon',
      '13:00–18:30',
      ' When ',
      ' Where ',
      ' Entry ',
      ' Source ',
      'Listing on hannover.de',
      'Checked Fri 09 Oct 11:00',
      'Map',
      `Also on ${weekday} ${dayNumber} ${month}`,
    );
    // Shown without JS: no hidden attribute before the decorative aria-hidden.
    expect(tiergarten).toContain('<p class="sheet__tile" data-sheet-tile aria-hidden="true"');
    expect(tiergarten).toMatch(/data-occasion-status[^>]*>\s*Coming soon\s*</);
    expect(tiergarten).toMatch(
      new RegExp(`<time datetime="${day(1)}T13:00"[^>]*>[^<]*· 13:00–18:30</time>`),
    );
    expect(tiergartenText).toContain('Tiergartenstraße 117');
    expect(tiergartenText).toContain('30559 Hannover');
    expect(tiergarten).toMatch(
      /<span lang="de"[^>]*>Mit Baumscheibe \(für Eichel- und Kastaniensammler\*innen\)<\/span>/,
    );
    expect(tiergartenText).toContain('€3');
    // Entry conditions read in English; the gate's German term stays.
    expect(tiergartenText).toContain(
      'With a tree slice, for acorn and chestnut collectors: free',
    );
    expect(tiergartenText).toContain('Adults: €3');
    expect(tiergartenText).toContain('Children up to age 14: €2');
    expect(tiergartenText).not.toContain('Erwachsene');
    // The tree-slice row is conditional; the page never calls entry free.
    expect(tiergartenText).not.toContain('Free entry');
    expect(tiergarten).toContain(
      'href="https://www.openstreetmap.org/search?query=Tiergartenstra%C3%9Fe%20117%2C%2030559%20Hannover"',
    );
    // Copy and share need JavaScript, so they start hidden.
    expect(tiergarten).toMatch(/<button[^>]*data-copy-address[^>]*hidden/);
    expect(tiergarten).toMatch(/<button[^>]*data-share[^>]*hidden/);
    // Onward: open on the same day first, one-offs before the season-long
    // Wies'n, by time; that day's hours on each row.
    const onward = tiergarten.slice(tiergarten.indexOf('id="onward-title"'));
    const onwardText = text(onward);
    before(onwardText, 'Frühmarkt', '10:00–16:00', 'Adventsbasar', '14:00–20:00', 'Lichterabend', 'Hours not listed');
    expect(onward).not.toContain('href="/special/kunst-kurbis-in-eldagsen/"');
    expect(onward).not.toContain('href="/special/hannover-wies-27n/"');
    expect(onward).toContain(`href="/special/#day-${day(1)}"`);
    expect(onwardText).toContain(`All 4 on ${weekday} ${dayNumber} ${month} →`);
    // Kunst & Kürbis shares no day: the general rows with status and dates.
    const kunstOnward = text(page('kunst-kurbis-in-eldagsen').split('id="onward-title"')[1]);
    expect(kunstOnward).toMatch(/^[^<]*More occasions/);
    expect(kunstOnward).not.toContain(' on ');
    expect(onward).not.toContain('href="/special/abgesagtes-fest/"');
    expect(onward).not.toContain('href="/special/gestern-vorbei/"');
    expect(onward).not.toContain('href="/special/verlegt-und-vorbei/"');
    expect(onward).toContain('href="/special/"');
    // Hannover itself is no day trip (the onward list may show one).
    const facts = tiergarten.slice(
      tiergarten.indexOf('<dl'),
      tiergarten.indexOf('</dl>'),
    );
    expect(facts).not.toContain('Day trip');

    const kunst = page('kunst-kurbis-in-eldagsen');
    expect(text(kunst)).toContain('Day trip · Springe');
    expect(text(kunst)).toContain('Free entry');
    expect(kunst).toContain('"isAccessibleForFree":true');
    expect(kunst).toContain('"addressLocality":"Springe"');

    const wiesn = text(page('hannover-wies-27n'));
    expect(wiesn).toContain('Selected dates only');
    expect(wiesn).not.toContain(' Entry ');
    expect(wiesn).not.toContain('Map');

    // A cancelled occasion keeps its facts and onward links, not its actions.
    const cancelled = page('abgesagtes-fest');
    expect(cancelled).toMatch(/data-occasion-status[^>]*>\s*Cancelled\s*</);
    expect(cancelled).not.toContain('openstreetmap.org');
    expect(cancelled).toContain('href="/special/"');

    // Expiry is read from the dates, not the status label, also without JS.
    for (const slug of ['gestern-vorbei', 'verlegt-und-vorbei']) {
      const ended = page(slug);
      expect(ended, slug).not.toContain('openstreetmap.org');
      expect(ended, slug).not.toContain('data-occasion-actions');
      expect(ended, slug).toContain('href="/special/"');
    }
    expect(page('verlegt-und-vorbei')).toMatch(
      /data-occasion-status[^>]*>\s*Rescheduled\s*</,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}, 120000);

test('the occasion index supports weekly browsing, truthful admission and no-JS navigation', async () => {
  const root = mkdtempSync(join(tmpdir(), 'occasion-index-'));
  const env = { ...process.env };
  for (const name of ['WEB_DATA_ROOT', 'WEB_DATA_MODE', 'WEB_DATA_MAX_AGE_DAYS'])
    delete env[name];
  const data = join(root, 'data');
  const outDir = join(root, 'dist');
  const berlinToday = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Berlin',
  }).format(new Date());
  const day = (offset: number) =>
    new Date(Date.parse(`${berlinToday}T12:00:00Z`) + offset * 86400000)
      .toISOString()
      .slice(0, 10);
  const occasion = (slug: string, offset: number, extra: Record<string, unknown> = {}) => ({
    id: `hannover-festivals:${slug}`,
    slug,
    name: slug,
    kind: 'festival',
    startDate: day(offset),
    endDate: day(offset),
    location: 'Parkbühne',
    description: `${slug} at Parkbühne. See the source for details.`,
    sourceUrl: `https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/${slug}`,
    status: 'upcoming',
    programmeCount: 0,
    locationCount: 0,
    programmePath: `occasions/${slug}.json`,
    preview: [],
    ...extra,
  });
  const longName =
    'Internationaler Feuerwerkswettbewerb Herrenhausen: Finale mit Musikbegleitung und Illumination';
  const weekday = new Date(`${berlinToday}T00:00:00Z`).getUTCDay();
  const followingMonday = 14 - (weekday + 6) % 7;
  const followingSunday = followingMonday + 6;
  // On a Sunday the following week starts on day 8, where two rows still open.
  const followingSlugs = [
    ['daily-market', 8],
    ['day-eight', 8],
    ['day-fourteen', 14],
    ['wiesn', followingSunday],
    ['winterwald', 20],
  ].filter(([, lastDay]) => Number(lastDay) >= followingMonday).map(([slug]) => slug);
  // Manifest order is deliberately not the index order.
  const occasions = [
    occasion('day-fourteen', 14, { name: longName }),
    occasion('day-thirty', 30),
    occasion('day-thirty-one', 31),
    occasion('abgesagt', 7, { sourceStatus: 'cancelled', admission: [{ price: 'free' }] }),
    occasion('day-eight', 8),
    occasion('kunst-kurbis-in-eldagsen', 7, {
      name: 'Kunst & Kürbis in Eldagsen',
      scheduleConfidence: 'continuous',
      occurrences: [{ date: day(7), startTime: '11:00', endTime: '17:00' }],
      place: {
        venue: 'Eldagser Hoflieferant',
        street: 'Lange Straße 142',
        postalCode: '31832',
        locality: 'Springe',
        municipality: 'Springe',
      },
      area: 'region',
      admission: [{ price: '€12', isFrom: true }],
    }),
    // Sparse: the envelope covers today, its next listed date is day 3.
    occasion('wiesn', -2, {
      name: "Hannover Wies'n",
      endDate: day(27),
      scheduleConfidence: 'discrete',
      occurrences: [
        { date: day(-2), startTime: '18:00' },
        { date: day(3), startTime: '18:00' },
        { date: day(7), startTime: '18:00', endTime: '20:00' },
        { date: day(followingSunday), startTime: '18:00', endTime: '20:00' },
      ],
      admission: [{ price: '€7' }, { label: 'Kinder bis 14 Jahre', price: 'free' }],
    }),
    occasion('daily-market', 4, {
      endDate: day(8),
      location: 'Bürgergemeinschaftshaus Ahlem',
      scheduleConfidence: 'continuous',
      occurrences: [{ date: day(4), startTime: '14:00' }],
    }),
    occasion('flohmarkt', -7, { endDate: day(7), scheduleConfidence: 'unknown' }),
    occasion('gestern-vorbei', -1),
    // Season-long and open today, hours listed only from tomorrow.
    occasion('winterwald', -3, {
      name: 'Winterwald',
      endDate: day(20),
      location: 'Weißekreuzplatz',
      scheduleConfidence: 'continuous',
      occurrences: [{ date: day(1), startTime: '11:00', endTime: '21:00' }],
    }),
    occasion('heute', 0, {
      place: {
        venue: 'Tiergarten',
        street: 'Tiergartenstraße 117',
        postalCode: '30559',
        locality: 'Hannover',
        municipality: 'Hannover',
      },
      area: 'city',
      admission: [{ price: 'free' }],
    }),
  ];
  try {
    mkdirSync(join(data, 'occasions'), { recursive: true });
    writeFileSync(
      join(data, 'web_events.json'),
      JSON.stringify({
        meta: {
          week: 41,
          year: 2026,
          updatedAt: 'Sun 11 Oct 09:00',
          updatedAtISO: `${day(0)}T00:30:00+02:00`,
        },
        movies: [],
        concerts: [],
        occasions,
      }),
    );
    for (const item of occasions)
      writeFileSync(
        join(data, item.programmePath),
        JSON.stringify({
          meta: { updatedAt: 'Sun 11 Oct 09:00' },
          occasion: item,
          programme: [],
        }),
      );
    const result = spawnSync(
      process.execPath,
      [
        join(projectRoot, 'node_modules/astro/bin/astro.mjs'),
        'build',
        '--root',
        projectRoot,
        '--outDir',
        outDir,
      ],
      {
        cwd: root,
        env: { ...env, WEB_DATA_ROOT: data, WEB_DATA_MODE: 'fixture' },
        encoding: 'utf8',
        timeout: 60000,
      },
    );
    if (result.error) throw result.error;
    expect(result.status, result.stdout + result.stderr).toBe(0);
    const html = readFileSync(join(outDir, 'special', 'index.html'), 'utf8');
    const text = (markup: string) =>
      markup
        .replace(/<script[\s\S]*?<\/script>/g, ' ')
        .replace(/<svg[\s\S]*?<\/svg>/g, ' ')
        .replace(/<[^>]+>/g, ' ')
        .replace(/&#39;/g, "'")
        .replace(/&amp;/g, '&')
        .replace(/\s+/g, ' ')
        .trim();
    const slugsIn = (markup: string) =>
      [...markup.matchAll(/data-index-row="([a-z0-9-]+)"/g)].map(([, slug]) => slug);
    const parts = Object.fromEntries(
      [...html.matchAll(/<section class="index-part[^"]*"[^>]*data-index-part="(\w+)"([^>]*)>([\s\S]*?)(?=<section class="index-part|<ol hidden data-index-pool)/g)]
        .map(([, key, attributes, body]) => [key, { hidden: / hidden(?=[ >])/.test(attributes), slugs: slugsIn(body), body }]),
    );
    const days = [...parts.days.body.matchAll(/<section class="index-day" id="day-([\d-]+)"[\s\S]*?<\/section>/g)]
      .map(([section, date]) => [date, text(section.match(/<h3[\s\S]*?<\/h3>/)![0]), slugsIn(section)]);

    // Season-long first, the rest under the day of their next confirmed date,
    // each occasion once; ended and beyond-horizon ones are gone.
    expect(Object.entries(parts).map(([key, { hidden, slugs }]) => [key, hidden, slugs])).toEqual([
      ['season', false, ['winterwald', 'wiesn']],
      ['days', false, ['heute', 'daily-market', 'kunst-kurbis-in-eldagsen', 'day-eight', 'day-fourteen', 'day-thirty']],
      ['check', false, ['flohmarkt']],
      ['off', false, ['abgesagt']],
    ]);
    // Without JS every date is absolute, true however long the page is served;
    // the browser adds Today, Open today and the 30-day wording.
    expect(days).toEqual([
      [day(0), dayHeading(day(0)), ['heute']],
      [day(4), dayHeading(day(4)), ['daily-market']],
      [day(7), dayHeading(day(7)), ['kunst-kurbis-in-eldagsen']],
      [day(8), dayHeading(day(8)), ['day-eight']],
      [day(14), dayHeading(day(14)), ['day-fourteen']],
      [day(30), dayHeading(day(30)), ['day-thirty']],
    ]);
    expect(text(html)).toContain(`8 occasions, ${sheetDateLine({ startDate: day(0), endDate: day(30) })}.`);
    expect(html).not.toContain('href="/special/gestern-vorbei/"');
    expect(html).not.toContain('href="/special/day-thirty-one/"');
    expect(text(html)).not.toMatch(/Open today|in the next 30 days/);

    const row = (slug: string) => {
      const start = html.lastIndexOf('<li', html.indexOf(`data-index-row="${slug}"`));
      return text(html.slice(start, html.indexOf('</li>', start)));
    };
    const dates = (from: number, to: number) =>
      sheetDateLine({ startDate: day(from), endDate: day(to) });
    const until = (offset: number) => `until ${dayHeading(day(offset)).replace(/^\w+ /, '')}`;
    // Separators between facts are drawn by CSS.
    expect(row('winterwald')).toBe(`${dayHeading(day(0))} Winterwald Weißekreuzplatz ${until(20)}`);
    expect(row('wiesn')).toBe(`Next open ${dayHeading(day(3))} Hannover Wies'n Parkbühne Check entry details ${until(27)}`);
    expect(row('heute')).toBe('heute Tiergarten Free entry');
    expect(row('kunst-kurbis-in-eldagsen')).toBe('11:00–17:00 Kunst & Kürbis in Eldagsen Eldagser Hoflieferant Day trip · Springe Entry from €12');
    expect(row('daily-market')).toBe(`from 14:00 daily-market Bürgergemeinschaftshaus Ahlem ${dates(4, 8)}`);
    expect(row('flohmarkt')).toBe(`${dates(-7, 7)} flohmarkt Parkbühne ${until(7)}`);
    expect(row('abgesagt')).toBe(`Cancelled · ${dates(7, 7)} abgesagt Parkbühne`);
    expect(html).toMatch(new RegExp(`lang="de"[^>]*>\\s*${longName}`));
    expect(html).toMatch(/<div class="index-empty"[^>]*\shidden/);

    const executablePath = process.env.CHROME_BIN;
    if (!executablePath && !process.env.CI) return;
    const server = Bun.serve({
      hostname: '127.0.0.1', port: 0,
      async fetch(request) {
        const path = new URL(request.url).pathname;
        const file = Bun.file(join(outDir, path.endsWith('/') ? `${path}index.html` : path));
        return await file.exists() ? new Response(file) : new Response('', { status: 404 });
      },
    });
    const origin = `http://127.0.0.1:${server.port}`;
    try {
      const browser = await chromium.launch(executablePath ? { executablePath } : { channel: 'chrome' });
      try {
        const noJs = await browser.newPage({ javaScriptEnabled: false });
        await noJs.goto(`${origin}/special/`);
        expect(await noJs.getByRole('group', { name: 'Browse by week' }).isVisible()).toBe(false);
        expect(await noJs.getByRole('link', { name: /Kunst & Kürbis.*Entry from €12/ }).isVisible()).toBe(true);
        expect(await noJs.getByRole('heading', { name: 'Check dates' }).isVisible()).toBe(true);
        expect(await noJs.getByRole('heading', { name: 'Cancelled or postponed' }).isVisible()).toBe(true);
        expect(await noJs.locator('[data-index-empty]').isVisible()).toBe(false);
        for (const path of ['/', '/special/', '/special/wiesn/', '/how-it-works/', '/impressum/', '/datenschutz/', '/404.html']) {
          await noJs.goto(`${origin}${path}`);
          const header = noJs.locator('header').first();
          const wordmark = header.getByRole('link', { name: /^boring hannover$/i });
          expect(await wordmark.getAttribute('href'), path).toBe('/');
          if (path === '/how-it-works/') {
            const footerBrand = noJs.locator('footer').getByRole('link', { name: 'Boring Hannover', exact: true });
            expect(await footerBrand.getAttribute('href')).toBe('/');
          }
          await wordmark.click();
          expect(new URL(noJs.url()).pathname).toBe('/');
        }
        await noJs.goto(`${origin}/special/`);
        await noJs.keyboard.press('Tab'); // Skip link
        await noJs.keyboard.press('Tab'); // The compact bar starts with the wordmark.
        const wordmark = noJs.getByRole('link', { name: /^boring hannover$/i });
        expect(await wordmark.evaluate(el => el === document.activeElement && getComputedStyle(el).outlineWidth === '2px')).toBe(true);
        await noJs.keyboard.press('Enter');
        await noJs.waitForURL(`${origin}/`);
        await noJs.close();

        const page = await browser.newPage({ viewport: { width: 1080, height: 800 } });
        await page.clock.install({ time: new Date(`${day(0)}T12:00:00Z`) });
        await page.goto(`${origin}/special/`);
        const cardLayout = () => page.locator('[data-index-week]').evaluateAll(cards => ({
          rows: new Set(cards.map(card => card.getBoundingClientRect().top)).size,
          datesBelow: cards.every(card => {
            const [name, dates] = Array.from(card.children, child => child.getBoundingClientRect());
            return dates.top >= name.bottom && card.getBoundingClientRect().height >= 44;
          }),
        }));
        await page.getByRole('group', { name: 'Browse by week' }).waitFor();
        expect(await cardLayout()).toEqual({ rows: 1, datesBelow: true });
        await page.setViewportSize({ width: 320, height: 800 });
        expect(await cardLayout()).toEqual({ rows: 1, datesBelow: true });
        const allDates = page.getByRole('button', { name: 'All dates', exact: true });
        const thisWeek = page.getByRole('button', { name: /^This week/ });
        const nextWeek = page.getByRole('button', { name: /^Next week/ });
        const followingWeek = page.getByRole('button', { name: /^Following week/ });
        const summary = page.locator('[data-index-summary]');
        const visibleRows = () => page.locator('[data-index-part]:not([hidden]) [data-index-row] a');
        const wiesn = visibleRows().filter({ hasText: "Hannover Wies'n" });
        const visibleHrefs = () => visibleRows().evaluateAll(links => links.map(link => link.getAttribute('href')));
        const visibleSlugs = async () => (await visibleHrefs()).map(href => href!.split('/')[2]).sort();
        const rowWhen = (slug: string) => page.locator(`[data-index-row="${slug}"] [data-index-when]`).textContent();
        expect(await allDates.getAttribute('aria-pressed')).toBe('true');
        expect(await summary.textContent()).toBe('8 occasions in the next 30 days.');
        expect(await rowWhen('winterwald')).toBe('Open today');
        expect(await page.locator('[data-index-row="winterwald"]').getAttribute('class')).toContain('index-row--open');
        expect(await rowWhen('wiesn')).toBe(`Next open ${dayHeading(day(3))}`);
        expect(await page.locator(`#day-${day(0)} [data-index-rel]`).textContent()).toBe('Today');
        expect(await page.locator(`#day-${day(7)} [data-index-rel]`).textContent()).toBe('in 7 days');
        expect(await visibleHrefs()).toContain('/special/day-thirty/');
        await thisWeek.click();
        expect(await visibleHrefs()).toContain(`/special/heute/?date=${day(0)}`);
        expect(await visibleHrefs()).toContain(`/special/winterwald/?date=${day(0)}`);
        expect(await visibleHrefs()).not.toContain('/special/day-thirty/');
        expect(await page.getByRole('heading', { name: 'Check dates' }).isVisible()).toBe(false);
        await nextWeek.click();
        expect(await visibleHrefs()).toContain(`/special/kunst-kurbis-in-eldagsen/?date=${day(7)}`);
        expect(await visibleHrefs()).not.toContain(`/special/heute/?date=${day(0)}`);
        await page.keyboard.press('Tab');
        expect(await followingWeek.evaluate(el => el === document.activeElement)).toBe(true);
        expect(await followingWeek.evaluate(el => getComputedStyle(el).outlineWidth)).toBe('2px');
        await page.keyboard.press('Space');
        expect(await followingWeek.getAttribute('aria-pressed')).toBe('true');
        expect(await nextWeek.getAttribute('aria-pressed')).toBe('false');
        expect(await visibleSlugs()).toEqual(followingSlugs);
        expect(await rowWhen('wiesn')).toBe(`${dayHeading(day(followingSunday))} · 18:00–20:00`);
        expect(await rowWhen('winterwald')).toBe(dayHeading(day(followingMonday)));
        expect(await summary.textContent()).toMatch(new RegExp(`^${followingSlugs.length} occasions following week, \\d`));
        expect(await page.getByRole('status').textContent()).toMatch(
          new RegExp(`^${followingSlugs.length} occasions · Following week, \\d`),
        );
        await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
        expect(await cardLayout()).toEqual({ rows: 3, datesBelow: true });
        await page.keyboard.press('Tab');
        expect(await visibleRows().first().evaluate(el => el === document.activeElement)).toBe(true);

        // A minute later nothing changed: the focused row is not moved.
        await page.clock.runFor(60_000);
        expect(await visibleRows().first().evaluate(el => el === document.activeElement)).toBe(true);
        const previousRange = await followingWeek.innerText();
        await wiesn.focus();
        await page.clock.setSystemTime(new Date(`${day(followingSunday)}T21:00:00Z`));
        await page.clock.runFor(60_000);
        expect(await wiesn.count()).toBe(0);
        expect(await followingWeek.evaluate(el => el === document.activeElement)).toBe(true);
        expect(await followingWeek.innerText()).not.toBe(previousRange);
        await page.clock.setSystemTime(new Date(`${day(21)}T12:00:00Z`));
        await page.clock.runFor(60_000);
        await thisWeek.click();
        expect(await visibleRows().count()).toBe(0);
        expect(await page.getByText(/^No upcoming confirmed occasions for /).isVisible()).toBe(true);
        await allDates.click();
        expect(await visibleHrefs()).toContain('/special/day-thirty/');
        expect(await page.locator('[data-index-row="winterwald"]').isVisible()).toBe(false);

        // A detail page's "All N on <day>" lands on everything open that day.
        await page.clock.setSystemTime(new Date(`${day(0)}T12:00:00Z`));
        await page.goto(`${origin}/special/wiesn/`);
        await page.goto(`${origin}/special/#day-${day(7)}`);
        await summary.filter({ hasText: ` on ${dayHeading(day(7))}.` }).waitFor();
        expect(await summary.textContent()).toBe(`4 occasions on ${dayHeading(day(7))}.`);
        expect(await allDates.getAttribute('aria-pressed')).toBe('false');
        expect(await visibleHrefs()).toEqual([
          `/special/wiesn/?date=${day(7)}`,
          `/special/winterwald/?date=${day(7)}`,
          `/special/kunst-kurbis-in-eldagsen/?date=${day(7)}`,
          `/special/daily-market/?date=${day(7)}`,
        ]);
        expect(await rowWhen('wiesn')).toBe(`${dayHeading(day(7))} · 18:00–20:00`);
        await allDates.click();
        expect(await summary.textContent()).toBe('8 occasions in the next 30 days.');
        expect(new URL(page.url()).hash).toBe('');
        // Also when the hash changes in place, e.g. on Back.
        await page.evaluate(date => { location.hash = `day-${date}`; }, day(4));
        await summary.filter({ hasText: ` on ${dayHeading(day(4))}.` }).waitFor();
        expect(await visibleSlugs()).toEqual(['daily-market', 'winterwald']);
        await allDates.click();

        // A new day removes today's section and moves the later ones up; the
        // focused row keeps focus.
        const kunst = visibleRows().filter({ hasText: 'Kunst & Kürbis' });
        await kunst.focus();
        await page.clock.setSystemTime(new Date(`${day(1)}T12:00:00Z`));
        await page.clock.runFor(60_000);
        expect(await page.locator(`#day-${day(0)}`).count()).toBe(0);
        expect(await kunst.evaluate(el => el === document.activeElement)).toBe(true);

        // The selected week links to a later opening than the detail's default.
        await page.clock.setSystemTime(new Date(`${day(0)}T12:00:00Z`));
        await page.clock.runFor(60_000);
        await followingWeek.click();
        await wiesn.click();
        expect(new URL(page.url()).searchParams.get('date')).toBe(day(followingSunday));
        const when = page.locator('[data-sheet-when]');
        const calendar = page.locator('[data-calendar-primary]');
        const appointment = `${dates(followingSunday, followingSunday)} · 18:00–20:00`;
        await when.filter({ hasText: appointment }).waitFor();
        expect(await when.innerText()).toBe(appointment);
        const calendarPath = `/special/wiesn/calendar/${day(followingSunday)}.ics`;
        expect(await calendar.getAttribute('href')).toBe(calendarPath);
        const download = await page.request.get(origin + calendarPath);
        expect(download.ok()).toBe(true);
        expect(await download.text()).toMatch(new RegExp(`^DTSTART:${day(followingSunday).replaceAll('-', '')}T`, 'm'));

        await calendar.focus();
        await page.clock.setSystemTime(new Date(`${day(followingSunday)}T21:00:00Z`));
        await page.clock.runFor(60_000);
        expect(await when.innerText()).toBe('Selected date is unavailable. Check the listed dates.');
        expect(await calendar.isVisible()).toBe(false);
        expect(await when.evaluate(el => el === document.activeElement)).toBe(true);

        await page.clock.setSystemTime(new Date(`${day(0)}T12:00:00Z`));
        await page.goto(`${origin}/special/wiesn/?date=${day(6)}`);
        expect(await when.innerText()).toBe('Selected date is unavailable. Check the listed dates.');
        expect(await calendar.isVisible()).toBe(false);
        await page.goto(`${origin}/special/daily-market/?date=${day(6)}`);
        await when.filter({ hasText: dates(6, 6) }).waitFor();
        expect(await when.innerText()).toBe(dates(6, 6));
        expect(await calendar.isVisible()).toBe(false);
        await page.goto(`${origin}/special/wiesn/`);
        expect(await calendar.getAttribute('href')).toBe(`/special/wiesn/calendar/${day(3)}.ics`);
      } finally {
        await browser.close();
      }
    } finally {
      server.stop(true);
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}, 120000);
