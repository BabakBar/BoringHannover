import { expect, test } from 'bun:test';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';
import type { Concert, OccasionSummary } from '../data/types';
import { dayHeading } from '../utils/occasionIndex';
import { addDays, berlinClock } from '../utils/occasionStatus';

const projectRoot = fileURLToPath(new URL('../../', import.meta.url));

test('the homepage board and day lists follow the reader clock, and start today (#114 §5)', async () => {
  const root = mkdtempSync(join(tmpdir(), 'occasion-board-'));
  const data = join(root, 'data');
  const outDir = join(root, 'dist');
  mkdirSync(join(data, 'occasions'), { recursive: true });
  const env = { ...process.env };
  for (const name of Object.keys(env)) {
    if (name.startsWith('WEB_DATA_') || name.startsWith('PUBLIC_UMAMI_')) delete env[name];
  }
  // The build and the fixture share the same Berlin today.
  const today = berlinClock(new Date()).date;
  const day = (offset: number) => addDays(today, offset);
  const short = (offset: number) => new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC', weekday: 'short', day: 'numeric',
  }).format(new Date(`${day(offset)}T00:00:00Z`));
  const occasion = (slug: string, offset: number, extra: Partial<OccasionSummary> = {}): OccasionSummary => ({
    id: `board:${slug}`, slug, name: slug, kind: 'festival',
    startDate: day(offset), endDate: day(offset), location: `${slug} venue`,
    description: 'See the source for details.', sourceUrl: 'https://example.com/festival',
    status: 'upcoming', programmeCount: 0, locationCount: 0,
    programmePath: `occasions/${slug}.json`, preview: [], ...extra,
  });
  const at = (offset: number, startTime?: string, endTime?: string) => ({
    scheduleConfidence: 'continuous' as const,
    occurrences: [{ date: day(offset), ...(startTime && { startTime }), ...(endTime && { endTime }) }],
  });
  // Manifest order is deliberately not the board order. Today's slots never
  // close before midnight, so the build's selection does not depend on its hour.
  const occasions = [
    occasion('weihnachtsmarkt', -10, { endDate: day(30), scheduleConfidence: 'continuous' }),
    occasion('nachtkonzert', 0, at(0, '17:00')),
    occasion('abendmarkt', 0, at(0, '14:00', '24:00')),
    occasion('adventsbasar', 0),
    occasion('fruehschoppen', 0, at(0, '12:00')),
    occasion('spaeter', 6),
    occasion('laternen', 5),
    occasion('eisbahn', 2, { endDate: day(20), ...at(2, '10:00', '20:00') }),
    occasion('kunst', 1, {
      name: 'Kunst & Kürbis', area: 'region',
      place: { venue: 'Hof', street: 'Lange Straße 1', postalCode: '31832', locality: 'Springe', municipality: 'Springe' },
    }),
    occasion('abgesagt', 1, { sourceStatus: 'cancelled' }),
    occasion('gestern', -1),
  ];
  const ddmm = (offset: number) => `${day(offset).slice(8, 10)}.${day(offset).slice(5, 7)}`;
  const movies = [-1, 0, 1, 2, 3, 4, 5].map(offset => ({
    day: 'X', date: ddmm(offset),
    movies: [{ title: `Film ${offset}`, time: '20:00', venue: 'Astor' }],
  }));
  const radar = (offset: number, count: number, radarCategory = 'Live Music'): Concert[] =>
    Array.from({ length: count }, (_, index) => ({
      title: `Event ${offset}.${index}`, date: `${Number(day(offset).slice(8, 10))} Nov`,
      dateISO: day(offset), day: 'So', venue: 'Venue', time: '20:00', radarCategory,
    }));
  // Yesterday fills the visible part, so the build splits today across the overflow.
  const concerts = [...radar(-1, 14), ...radar(0, 4), ...radar(1, 6, 'Market'), ...radar(2, 4), ...radar(3, 5), ...radar(4, 2)];
  const meta = { week: 47, year: 2026, updatedAt: 'Board fixture', updatedAtISO: `${day(-1)}T09:00:00+01:00` };
  for (const item of occasions) {
    writeFileSync(join(data, item.programmePath), JSON.stringify({ meta, occasion: item, programme: [] }));
  }
  writeFileSync(join(data, 'web_events.json'), JSON.stringify({ meta, movies, concerts, occasions }));
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
    const build = spawnSync(process.execPath, [
      join(projectRoot, 'node_modules/astro/bin/astro.mjs'), 'build', '--root', projectRoot, '--outDir', outDir,
    ], { cwd: root, encoding: 'utf8', timeout: 60000, env: { ...env, WEB_DATA_ROOT: data, WEB_DATA_MODE: 'fixture' } });
    if (build.error) throw build.error;
    expect(build.status, build.stdout + build.stderr).toBe(0);
    expect(readFileSync(join(outDir, 'index.html'), 'utf8')).not.toContain('href="/special/gestern/"');

    const executablePath = process.env.CHROME_BIN;
    if (!executablePath && !process.env.CI) return;
    const browser = await chromium.launch(executablePath ? { executablePath } : { channel: 'chrome' });
    try {
      const rows = (page: import('playwright-core').Page, part: 'today' | 'coming') =>
        page.locator(`[data-board-${part}] [data-board-row]`).evaluateAll(items => items.map(item => [
          item.getAttribute('data-board-row'),
          item.querySelector('[data-board-when]')!.textContent,
          item.querySelector('[data-board-end]')!.textContent,
          item.querySelector('a')!.getAttribute('href'),
        ]));
      const board = (page: import('playwright-core').Page) => page.locator('[data-board]');

      // Without JS: the build's own selection, absolute dates, no time-of-day labels.
      const plain = await browser.newPage({ javaScriptEnabled: false, viewport: { width: 390, height: 900 } });
      await plain.goto(origin);
      expect(await rows(plain, 'today')).toEqual([
        ['fruehschoppen', '12:00', '', '/special/fruehschoppen/'],
        ['abendmarkt', '14:00', '–24:00', '/special/abendmarkt/'],
        ['nachtkonzert', '17:00', '', '/special/nachtkonzert/'],
        ['adventsbasar', short(0), '', '/special/adventsbasar/'],
      ]);
      expect(await rows(plain, 'coming')).toEqual([
        ['kunst', short(1), '', `/special/kunst/?date=${day(1)}`],
        ['eisbahn', short(2), '10:00', `/special/eisbahn/?date=${day(2)}`],
        ['laternen', short(5), '', `/special/laternen/?date=${day(5)}`],
      ]);
      const plainText = await board(plain).innerText();
      expect(plainText).toContain(dayHeading(day(0)).toUpperCase());
      expect(plainText).not.toMatch(/ON NOW|FROM \d|TODAY/);
      expect(await plain.locator('[data-board-more]').innerText()).toBe('+1 MORE');
      expect(await plain.locator('[data-board-all]').innerText()).toBe('ALL 9 CITY OCCASIONS →');
      expect(await plain.locator('[data-board-row="kunst"]').innerText()).toContain('Day trip · Springe');
      expect(await plain.locator('[data-board-row="eisbahn"] [data-board-opens]').isVisible()).toBe(true);
      expect(await plain.locator('[data-board-fallback]').isVisible()).toBe(false);
      // Every day stays without JS.
      expect(await plain.getByText('Film -1').isVisible()).toBe(true);
      await plain.close();

      const page = await browser.newPage({ viewport: { width: 390, height: 900 } });
      await page.clock.install({ time: new Date(`${day(0)}T14:00:00Z`) });
      await page.goto(origin);
      await page.locator('[data-board-today-label]').filter({ hasText: /^Today$/ }).waitFor();
      expect(await rows(page, 'today')).toEqual([
        ['fruehschoppen', 'From 12:00', '', '/special/fruehschoppen/'],
        ['abendmarkt', 'On now', '–24:00', '/special/abendmarkt/'],
        ['nachtkonzert', '17:00', '', '/special/nachtkonzert/'],
        ['adventsbasar', 'Today', '', '/special/adventsbasar/'],
      ]);
      expect(await page.locator('[data-board-row="abendmarkt"] a').getAttribute('class')).toContain('board-row--now');
      expect(await page.locator('[data-board-more]').innerText()).toBe('+1 MORE TODAY');

      // Movies and Radar start today, refilled from the overflow.
      const days = (section: string) => page.locator(`#${section}-visible > [data-day-date]:not([hidden])`)
        .evaluateAll(groups => groups.map(group => group.getAttribute('data-day-date')));
      expect(await days('movies')).toEqual([day(0), day(1), day(2)]);
      const moviesToggle = page.locator('#movies-toggle');
      expect(await moviesToggle.innerText()).toContain('+3 MORE DAYS');
      await moviesToggle.click();
      await moviesToggle.click();
      await page.clock.runFor(1000);
      expect(await moviesToggle.innerText()).toContain('+3 MORE DAYS');
      // Today was split at build time; it continues under one heading.
      expect(await days('events')).toEqual([day(0), day(1), day(2), day(3)]);
      expect(await page.locator(`#events-visible > [data-day-date="${day(0)}"] [data-event-item]`).count()).toBe(4);
      const radarToggle = page.locator('#radar-toggle');
      expect(await radarToggle.innerText()).toContain('+2 MORE');
      // A category filter keeps the toggle hidden across refreshes.
      await page.getByRole('button', { name: /^Market/ }).click();
      await page.clock.runFor(60_000);
      expect(await radarToggle.isVisible()).toBe(false);
      await page.getByRole('button', { name: /^All/ }).click();
      expect(await radarToggle.isVisible()).toBe(true);

      // 320 px with 200 % text: nothing overflows, every board link is a 44 px target.
      await page.setViewportSize({ width: 320, height: 800 });
      await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
      expect(await board(page).locator('a').evaluateAll(links =>
        links.filter(link => link.checkVisibility() && link.getBoundingClientRect().height < 44).length)).toBe(0);
      await page.evaluate(() => { document.documentElement.style.fontSize = ''; });

      // The minute refresh keeps focus; a row moving from Coming up to Today keeps it too.
      const kunst = page.locator('[data-board-row="kunst"] a');
      await kunst.focus();
      await page.clock.runFor(60_000);
      expect(await kunst.evaluate(el => el === document.activeElement)).toBe(true);
      await page.clock.setSystemTime(new Date(`${day(1)}T09:00:00Z`));
      await page.clock.runFor(60_000);
      expect((await rows(page, 'today')).map(([slug]) => slug)).toEqual(['kunst', 'weihnachtsmarkt']);
      expect(await kunst.evaluate(el => el === document.activeElement)).toBe(true);
      expect((await rows(page, 'coming')).map(([slug]) => slug)).toEqual(['eisbahn', 'laternen', 'spaeter']);
      expect(await page.locator('[data-board-date]').innerText()).toBe(dayHeading(day(1)).toUpperCase());
      expect(await page.locator('[data-board-more]').isVisible()).toBe(false);

      // Later: the edition is past and the occasions are over.
      await page.clock.setSystemTime(new Date(`${day(40)}T12:00:00Z`));
      await page.clock.runFor(60_000);
      expect(await page.getByText('No upcoming screenings in this edition.').isVisible()).toBe(true);
      expect(await page.getByText('No upcoming events in this edition.').isVisible()).toBe(true);
      expect(await moviesToggle.isVisible()).toBe(false);
      expect(await board(page).isVisible()).toBe(false);
      expect(await page.locator('[data-board-fallback] a').isVisible()).toBe(true);
      expect(await kunst.evaluate(el => el === document.activeElement)).toBe(false);
      expect(await page.locator('[data-board-fallback] a').evaluate(el => el === document.activeElement)).toBe(true);
    } finally {
      await browser.close();
    }
  } finally {
    server.stop(true);
    rmSync(root, { recursive: true, force: true });
  }
}, 120000);
