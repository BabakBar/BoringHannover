import { expect, test } from 'bun:test';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, type Browser } from 'playwright-core';
import { addDays, berlinClock } from '../utils/occasionStatus';
import { sheetDateLine } from '../utils/occasionSheet';
import type { OccasionSummary } from '../data/types';

const projectRoot = fileURLToPath(new URL('../../', import.meta.url));
const executablePath = process.env.CHROME_BIN;

test.skipIf(!executablePath && !process.env.CI)(
  'homepage cards show confirmed appointments and keep dates truthful as the Berlin clock advances',
  async () => {
    const root = mkdtempSync(join(tmpdir(), 'occasion-spotlight-'));
    const data = join(root, 'data');
    const outDir = join(root, 'dist');
    mkdirSync(join(data, 'occasions'), { recursive: true });
    const today = berlinClock(new Date()).date;
    const day = (offset: number) => addDays(today, offset);
    const dateText = (date: string) => new Intl.DateTimeFormat('en-GB', {
      timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short',
    }).format(new Date(`${date}T12:00:00Z`));
    const occasion = (slug: string, extra: Partial<OccasionSummary> = {}): OccasionSummary => ({
      id: `spotlight:${slug}`, slug, name: slug, kind: 'festival',
      startDate: day(0), endDate: day(30), location: 'Hannover',
      description: 'See the source for details.', sourceUrl: 'https://example.com/festival',
      status: 'upcoming', programmeCount: 0, locationCount: 0,
      programmePath: `occasions/${slug}.json`, preview: [], ...extra,
    });
    const sparse = occasion('selected-weekends', {
      name: 'Internationaler Feuerwerkswettbewerb Herrenhausen mit Musikbegleitung',
      scheduleConfidence: 'discrete',
      occurrences: [
        { date: day(3), startTime: '18:00', endTime: '20:00' },
        { date: day(5) },
      ],
    });
    const continuous = occasion('daily-festival', {
      startDate: day(3), endDate: day(8), scheduleConfidence: 'continuous',
      occurrences: [{ date: day(3), startTime: '18:00', endTime: '20:00' }],
    });
    const cases = [
      { occasion: sparse, when: `${dateText(day(3))} · 18:00–20:00`, span: `Selected dates · ${sheetDateLine(sparse)}` },
      { occasion: continuous, when: `${dateText(day(3))} · 18:00–20:00`, span: sheetDateLine(continuous) },
      { occasion: occasion('unknown-hours', { startDate: day(-3), scheduleConfidence: 'unknown' }), when: 'Check source for dates' },
      { occasion: occasion('cancelled', { ...sparse, id: 'spotlight:cancelled', slug: 'cancelled', programmePath: 'occasions/cancelled.json', sourceStatus: 'cancelled' }), when: 'Check source for dates', span: `Selected dates · ${sheetDateLine(sparse)}`, visible: false },
      { occasion: occasion('postponed', { sourceStatus: 'postponed', startDate: day(3) }), when: 'Check source for dates', visible: false },
      { occasion: occasion('ended', { startDate: day(-2), endDate: day(-1), sourceStatus: 'rescheduled' }), when: 'Ended', visible: false },
      { occasion: occasion('date-only', { startDate: day(30), endDate: day(30) }), when: dateText(day(30)), span: null },
      { occasion: occasion('outside-horizon', { startDate: day(31), endDate: day(31), scheduleConfidence: 'discrete', occurrences: [{ date: day(31), startTime: '18:00' }] }), when: 'Check source for dates', span: `Selected dates · ${sheetDateLine({ startDate: day(31), endDate: day(31) })}`, visible: false },
    ];
    const env = { ...process.env };
    for (const name of Object.keys(env)) {
      if (name.startsWith('WEB_DATA_') || name.startsWith('PUBLIC_UMAMI_')) delete env[name];
    }
    const meta = { week: 45, year: 2026, updatedAt: 'Spotlight fixture', updatedAtISO: new Date().toISOString() };
    const server = Bun.serve({
      hostname: '127.0.0.1', port: 0,
      async fetch(request) {
        const path = new URL(request.url).pathname;
        const file = Bun.file(join(outDir, path.endsWith('/') ? `${path}index.html` : path));
        return await file.exists() ? new Response(file) : new Response('', { status: 404 });
      },
    });
    const origin = `http://127.0.0.1:${server.port}`;
    let browser: Browser | undefined;
    try {
      browser = await chromium.launch(executablePath ? { executablePath } : { channel: 'chrome' });
      for (let offset = 0; offset < cases.length; offset += 2) {
        const pair = cases.slice(offset, offset + 2);
        const reserve = occasion('later-festival', { startDate: day(20), endDate: day(20) });
        const inventory = [...pair.map(item => item.occasion), ...(offset === 0 ? [reserve] : [])];
        for (const occasion of inventory) {
          writeFileSync(join(data, occasion.programmePath), JSON.stringify({ meta, occasion, programme: [] }));
        }
        writeFileSync(join(data, 'web_events.json'), JSON.stringify({
          meta, movies: [], concerts: [], occasions: inventory,
        }));
        const build = spawnSync(process.execPath, [
          join(projectRoot, 'node_modules/astro/bin/astro.mjs'),
          'build', '--root', projectRoot, '--outDir', outDir,
        ], {
          cwd: root, encoding: 'utf8', timeout: 30000,
          env: { ...env, WEB_DATA_ROOT: data, WEB_DATA_MODE: 'production', PUBLIC_UMAMI_WEBSITE_ID: '00000000-0000-4000-8000-000000000054' },
        });
        if (build.error) throw build.error;
        expect(build.status, build.stdout + build.stderr).toBe(0);
        expect(readFileSync(join(outDir, 'index.html'), 'utf8')).not.toContain('23cf1ce2-3635-4e97-aab9-6ccd0467f839');

        const plain = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 900 } });
        await plain.route('**/*', route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
        const page = await plain.newPage();
        page.setDefaultTimeout(5000);
        await page.goto(origin);
        for (const item of pair) {
          const card = page.locator(`.occasion-spotlight:has(a[href="/special/${item.occasion.slug}/"])`);
          if (item.occasion.endDate < today) {
            expect(await card.count()).toBe(0);
            continue;
          }
          expect(await card.isVisible()).toBe(item.visible !== false);
          expect((await card.locator('.occasion-spotlight__date').textContent())?.trim()).toBe(item.when);
          const span = card.locator('[data-spotlight-span]');
          expect(await span.isVisible()).toBe(item.visible !== false && item.span !== null);
          expect((await span.textContent())?.trim()).toBe(item.span ?? (item.span === null ? '' : sheetDateLine(item.occasion)));
          expect(await card.locator('a').getAttribute('href')).toBe(`/special/${item.occasion.slug}/`);
        }
        if (offset === 0) expect(await page.locator('.occasion-spotlight').nth(2).isVisible()).toBe(false);
        await plain.close();

        if (offset === 6) {
          const context = await browser.newContext();
          await context.route('**/*', route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
          const page = await context.newPage();
          await page.clock.install({ time: new Date(`${day(0)}T12:00:00Z`) });
          await page.goto(origin);
          expect(await page.locator('.occasion-spotlight').nth(0).isVisible()).toBe(true);
          expect(await page.locator('.occasion-spotlight').nth(1).isVisible()).toBe(false);
          await page.clock.setSystemTime(new Date(`${day(1)}T12:00:00Z`));
          await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
          expect(await page.locator('.occasion-spotlight').nth(1).isVisible()).toBe(true);
          await context.close();
        }
        if (offset !== 0) continue;
        const context = await browser.newContext({ viewport: { width: 390, height: 900 } });
        await context.route('**/*', route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
        const live = await context.newPage();
        live.setDefaultTimeout(5000);
        await live.clock.install({ time: new Date(`${day(3)}T12:00:00Z`) });
        await live.goto(origin);
        const cards = live.locator('.occasion-spotlight');
        await cards.nth(0).getByRole('link').focus();
        expect(await cards.nth(0).locator('[data-spotlight-when]').textContent()).toBe(`${dateText(day(3))} · 18:00–20:00`);
        await live.clock.runFor(60_000);
        await live.clock.setSystemTime(new Date(`${day(3)}T21:00:00Z`));
        await live.clock.runFor(60_000);
        expect(await cards.nth(0).locator('[data-spotlight-when]').textContent()).toBe(dateText(day(5)));
        expect(await cards.nth(1).locator('[data-spotlight-when]').textContent()).toBe(dateText(day(4)));
        expect(await cards.nth(0).locator('[data-occasion-status]').textContent()).toBe('In 2 days');
        expect(await cards.nth(0).getByRole('link').evaluate(el => el === document.activeElement)).toBe(true);
        // Midnight is a Berlin calendar boundary, including either DST offset.
        const utcMidnight = new Date(`${day(5)}T00:00:00Z`);
        const midnight = utcMidnight.getTime() - berlinClock(utcMidnight).minutes * 60_000;
        await live.clock.setSystemTime(new Date(midnight - 30_000));
        await live.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
        await live.clock.runFor(60_000);
        expect(await cards.nth(1).locator('[data-spotlight-when]').textContent()).toBe(dateText(day(5)));
        await live.clock.setSystemTime(new Date(`${day(6)}T12:00:00Z`));
        await live.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
        expect(await cards.nth(0).locator('[data-spotlight-when]').textContent()).toBe('Check source for dates');
        expect(await cards.nth(0).locator('[data-occasion-status]').textContent()).toBe('Check dates');
        expect(await cards.nth(0).isVisible()).toBe(false);
        expect(await cards.nth(1).isVisible()).toBe(true);
        expect(await cards.nth(2).isVisible()).toBe(true);
        expect(await cards.nth(1).getAttribute('class')).not.toContain('occasion-spotlight--compact');
        expect(await cards.nth(2).getAttribute('class')).toContain('occasion-spotlight--compact');
        for (const width of [320, 390, 1280]) {
          await live.setViewportSize({ width, height: 900 });
          for (const fontSize of ['16px', '32px']) {
            await live.evaluate(value => { document.documentElement.style.fontSize = value; }, fontSize);
            for (const text of await live.locator('.occasion-spotlight:not([hidden])').locator('h2, .occasion-spotlight__eyebrow, [data-spotlight-when], [data-spotlight-span]').all()) {
              const size = await text.evaluate(el => ({ text: el.textContent, content: el.scrollWidth, width: el.clientWidth }));
              expect(size.content, JSON.stringify({ viewport: width, fontSize, ...size })).toBeLessThanOrEqual(size.width);
            }
          }
        }
        await live.clock.setSystemTime(new Date(`${day(32)}T12:00:00Z`));
        await live.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
        expect(await live.locator('.occasion-spotlight:not([hidden])').count()).toBe(0);
        expect(await live.getByRole('link', { name: 'See all City Occasions' }).isVisible()).toBe(true);
        expect(await live.locator('[data-occasion-index-link]').getAttribute('class')).not.toContain('-mt-6');
        await context.close();
      }
    } finally {
      await browser?.close();
      server.stop(true);
      rmSync(root, { recursive: true, force: true });
    }
  },
  180000,
);
