import { expect, test } from 'bun:test';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, type Browser } from 'playwright-core';
import { addDays, berlinClock } from '../utils/occasionStatus';

const projectRoot = fileURLToPath(new URL('../../', import.meta.url));
const executablePath = process.env.CHROME_BIN;

test.skipIf(!executablePath && !process.env.CI)(
  'occasion dates and conditions stay readable with keyboard, no JS and enlarged text',
  async () => {
    const root = mkdtempSync(join(tmpdir(), 'occasion-sheet-'));
    const data = join(root, 'data');
    const dist = join(root, 'dist');
    mkdirSync(join(data, 'occasions'), { recursive: true });
    const today = berlinClock(new Date()).date;
    const day = (offset: number) => addDays(today, offset);
    const hoursText = 'Geöffnet nach Vereinbarung. '.repeat(14) + 'Geschlossen am 25.12.2026.';
    const meta = { week: 45, year: 2026, updatedAt: 'Sheet fixture', updatedAtISO: new Date().toISOString() };
    const base = {
      kind: 'festival', name: 'Weihnachtsdorf auf dem Lindener Berg',
      startDate: day(1), endDate: day(8), location: 'Lindener Turm',
      description: 'See the source for details.', sourceUrl: 'https://www.hannover.de/occasion',
      status: 'upcoming', programmeCount: 0, locationCount: 0, preview: [],
    };
    const occasions = [
      { ...base, slug: 'many-dates', scheduleConfidence: 'discrete',
        occurrences: Array.from({ length: 8 }, (_, index) => ({ date: day(index + 1), startTime: '17:00', endTime: '22:00' })),
        admission: [{ label: 'Erwachsene', price: '€23.80', isFrom: true }, { label: 'Kinder (5-17 Jahre)', price: '€14.80', isFrom: true }] },
      { ...base, slug: 'unknown-hours', scheduleConfidence: 'unknown', hoursText },
      { ...base, slug: 'partial-hours', scheduleConfidence: 'continuous',
        occurrences: [1, 2, 3].map(offset => ({ date: day(offset), startTime: '11:00', endTime: '21:00' })) },
      { ...base, slug: 'ended-dates', startDate: day(-8), endDate: day(-1),
        status: 'ended', scheduleConfidence: 'discrete',
        occurrences: Array.from({ length: 8 }, (_, index) => ({ date: day(index - 8), startTime: '17:00' })) },
    ].map(item => ({ ...item, id: `sheet:${item.slug}`, programmePath: `occasions/${item.slug}.json` }));
    for (const occasion of occasions) {
      writeFileSync(join(data, occasion.programmePath), JSON.stringify({ meta, occasion, programme: [] }));
    }
    writeFileSync(join(data, 'web_events.json'), JSON.stringify({ meta, movies: [], concerts: [], occasions }));
    const env = { ...process.env };
    for (const key of Object.keys(env)) {
      if (key.startsWith('WEB_DATA_') || key.startsWith('PUBLIC_UMAMI_')) delete env[key];
    }
    const build = spawnSync(process.execPath, [join(projectRoot, 'node_modules/astro/bin/astro.mjs'), 'build', '--root', projectRoot, '--outDir', dist], {
      cwd: root, encoding: 'utf8', timeout: 30000,
      env: { ...env, WEB_DATA_ROOT: data, WEB_DATA_MODE: 'production', PUBLIC_UMAMI_WEBSITE_ID: '00000000-0000-4000-8000-000000000039' },
    });
    expect(build.status, build.stdout + build.stderr).toBe(0);
    expect(readFileSync(join(dist, 'special/many-dates/index.html'), 'utf8')).not.toContain('23cf1ce2-3635-4e97-aab9-6ccd0467f839');
    const server = Bun.serve({ hostname: '127.0.0.1', port: 0, async fetch(request) {
      const path = new URL(request.url).pathname;
      const file = Bun.file(join(dist, path.endsWith('/') ? `${path}index.html` : path));
      return await file.exists() ? new Response(file) : new Response('', { status: 404 });
    } });
    const origin = `http://127.0.0.1:${server.port}`;
    let browser: Browser | undefined;
    try {
      browser = await chromium.launch(executablePath ? { executablePath } : { channel: 'chrome' });
      for (const javaScriptEnabled of [false, true]) {
        const context = await browser.newContext({ javaScriptEnabled, viewport: { width: 320, height: 800 } });
        await context.route('**/*', route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
        const page = await context.newPage();
        await page.goto(`${origin}/special/many-dates/`);
        expect(await page.locator('[data-schedule-preview] > li:visible').count()).toBe(3);
        expect(await page.locator('[data-schedule-more] li:visible').count()).toBe(0);
        expect(await page.locator('.sheet__facts').innerText()).toContain('from €23.80');
        const summary = page.locator('[data-schedule-more] > summary');
        await summary.focus();
        await page.keyboard.press('Enter');
        expect(await page.locator('[data-schedule-more] li:visible').count()).toBe(5);
        expect(await summary.evaluate(element => document.activeElement === element)).toBe(true);
        expect((await summary.boundingBox())!.height).toBeGreaterThanOrEqual(44);
        if (javaScriptEnabled) {
          await page.clock.install({ time: new Date(`${day(4)}T12:00:00Z`) });
          await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
          expect(await page.locator('[data-schedule-preview] > li:visible').evaluateAll(items => items.map(item => item.getAttribute('data-occurrence-date')))).toEqual([day(4), day(5), day(6)]);
          expect(await page.locator('[data-schedule-more] li:visible').count()).toBe(2);
          await page.clock.setSystemTime(new Date(`${day(6)}T12:00:00Z`));
          await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
          expect(await summary.evaluate(element => document.activeElement === element)).toBe(true);
          expect(await page.locator('[data-schedule-empty]').isVisible()).toBe(true);
        }
        await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
        await page.evaluate(() => document.fonts.ready);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        expect(await page.locator('header').first().getByText('boring hannover', { exact: true }).evaluate(element => {
          const text = element.getBoundingClientRect();
          const container = element.parentElement!.getBoundingClientRect();
          return text.left >= container.left - 1 && text.right <= container.right + 1;
        })).toBe(true);
        await page.goto(`${origin}/special/unknown-hours/`);
        const sourceSchedule = page.locator('[data-source-schedule] > summary');
        await sourceSchedule.focus();
        await page.keyboard.press('Enter');
        expect(await page.locator('[data-source-schedule]').innerText()).toContain(hoursText);
        await page.goto(`${origin}/special/partial-hours/`);
        expect(await page.locator('.sheet__facts').innerText()).not.toContain('daily');
        await page.goto(`${origin}/special/ended-dates/`);
        expect(await page.locator('meta[name="robots"]').getAttribute('content')).toBe('noindex, follow');
        expect(await page.locator('[data-occasion-actions]').count()).toBe(0);
        expect(await page.locator('[data-schedule-preview] > li:visible').count()).toBe(3);
        await page.locator('[data-schedule-more] > summary').focus();
        await page.keyboard.press('Enter');
        expect(await page.locator('[data-schedule-more] li:visible').count()).toBe(5);
        await context.close();
      }
    } finally {
      await browser?.close();
      server.stop(true);
      rmSync(root, { recursive: true, force: true });
    }
  }, 60000,
);
