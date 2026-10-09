import { expect, test } from 'bun:test';
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const projectRoot = fileURLToPath(new URL('../../', import.meta.url));
test('Astro build selects the anchored root, rejects missing production data, and labels mock HTML', () => {
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
    expect(html).not.toContain('Development preview');
    expect(html).not.toContain(projectRoot);
    const missing = join(root, 'missing');
    const rejected = build({
      WEB_DATA_ROOT: missing,
      WEB_DATA_MODE: 'production',
    });
    expect(rejected.status).not.toBe(0);
    expect(rejected.log).toContain(join(missing, 'web_events.json'));
    expect(rejected.log).toContain('mock fallback forbidden');
    const mock = build({ WEB_DATA_ROOT: missing, WEB_DATA_MODE: 'mock' });
    expect(mock.status).toBe(0);
    const mockHtml = readFileSync(join(outDir, 'index.html'), 'utf8');
    expect(mockHtml).toContain('Development preview');
    expect(mockHtml).toContain('&quot;source&quot;:&quot;mock&quot;');
    expect(mockHtml).not.toContain(missing);
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
  const occasion = (slug: string, extra: Record<string, unknown>) => ({
    id: `hannover-festivals:${slug}`,
    slug,
    name: slug,
    kind: 'festival',
    startDate: '2026-10-09',
    endDate: '2026-10-17',
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
        { date: '2026-10-09', startTime: '18:00' },
        { date: '2026-10-16', startTime: '18:00' },
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
      /<time datetime="2026-10-09T18:00"[^>]*>\s*Fri 9 Oct, 18:00\s*<\/time>/,
    );
    expect(wiesn).toMatch(/<time datetime="2026-10-16T18:00"[^>]*>/);

    expect(page('flohmarkt')).toMatch(
      /<span lang="de"[^>]*>04\.10\.2026 bis 18\.10\.2026 ab 08:00 bis 17:00 Uhr sonntags<\/span>/,
    );
    expect(readFileSync(join(outDir, 'index.html'), 'utf8')).toContain(
      'data-occasion-status',
    );
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
  const occasion = (slug: string, extra: Record<string, unknown>) => ({
    id: `hannover-festivals:${slug}`,
    slug,
    name: slug,
    kind: 'festival',
    startDate: '2026-10-10',
    endDate: '2026-10-10',
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
  const hostile = '</script><!--<script>alert(1)</script>';
  const occasions = [
    // Old snapshots still carry a third-party photo.
    occasion('tiergartenfest-hannover', {
      name: 'Tiergartenfest Hannover',
      description: 'Tiergartenfest Hannover at Tiergarten. See the source for details.',
      imageUrl:
        'https://www.hannover.de/var/storage/images/_aliases/full/Tiergartenfest 05.jpg.webp',
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
    const ownedImage = 'https://boringhannover.de/brand/og-image-1200x630.png';
    expect(meta(tiergarten, 'og:image')).toBe(ownedImage);
    expect(meta(tiergarten, 'twitter:image')).toBe(ownedImage);
    expect(tiergarten).not.toContain('var/storage/images');
    const tiergartenEvent = eventJsonLd(tiergarten);
    expect(tiergartenEvent).not.toHaveProperty('image');
    expect(tiergartenEvent.location).toEqual({ '@type': 'Place', name: 'Tiergarten' });
    expect(meta(tiergarten, 'description')).toBe(
      'Tiergartenfest Hannover at Tiergarten. See the source for details.',
    );
    expect(tiergarten).not.toContain('catching up');
    expect(tiergarten).toContain('Official event listing');
    expect(tiergarten).toMatch(/>\s*Listing on hannover\.de\s*</);
    expect(tiergarten).not.toContain('Official Tiergartenfest Hannover website');

    const maschsee = page('maschseefest-2026');
    expect(maschsee).toMatch(/>\s*Official website\s*</);
    expect(maschsee).not.toContain('Listing on hannover.de');
    // English wrapper that names the authoritative event.
    expect(meta(maschsee, 'description')).toBe(
      "Maschseefest: Music, food, family moments and late nights around Hannover's lake.",
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
