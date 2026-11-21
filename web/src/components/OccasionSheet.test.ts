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
  'occasion sheets lead with a usable date and preserve the full schedule with keyboard and no JS',
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
      { ...base, slug: 'many-dates', startDate: day(-2), scheduleConfidence: 'discrete',
        occurrences: [-2, -1, 1, 2, 3, 4, 5, 6, 7, 8].map(offset => ({ date: day(offset), startTime: '17:00', endTime: '22:00' })),
        admission: [{ label: 'Erwachsene', price: '€23.80', isFrom: true }, { label: 'Kinder (5-17 Jahre)', price: '€14.80', isFrom: true }] },
      { ...base, slug: 'unknown-hours', scheduleConfidence: 'unknown', hoursText },
      { ...base, slug: 'partial-hours', scheduleConfidence: 'continuous',
        occurrences: [1, 2, 3].map(offset => ({ date: day(offset), startTime: '11:00', endTime: '21:00' })) },
      { ...base, slug: 'daily-hours', endDate: day(3), scheduleConfidence: 'continuous',
        occurrences: [1, 2, 3].map(offset => ({ date: day(offset), startTime: '11:00', endTime: '21:00' })) },
      ...['cancelled', 'postponed', 'rescheduled'].map(sourceStatus => ({
        ...base, slug: sourceStatus, sourceStatus, scheduleConfidence: 'discrete',
        occurrences: [{ date: day(1), startTime: '17:00' }],
      })),
      { ...base, slug: 'date-only', startDate: day(1), endDate: day(1), scheduleConfidence: 'unknown' },
      { ...base, slug: 'exhausted-dates', startDate: day(-2), scheduleConfidence: 'discrete',
        occurrences: [{ date: day(-1), startTime: '17:00' }] },
      ...[30, 31].map(offset => ({
        ...base, slug: `day-${offset}`, startDate: day(offset), endDate: day(offset),
        scheduleConfidence: 'continuous', occurrences: [{ date: day(offset), startTime: '17:00' }],
      })),
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
    const dateText = (offset: number) => new Intl.DateTimeFormat('en-GB', {
      timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short',
    }).format(new Date(`${day(offset)}T12:00:00Z`));
    let browser: Browser | undefined;
    try {
      browser = await chromium.launch(executablePath ? { executablePath } : { channel: 'chrome' });
      for (const javaScriptEnabled of [false, true]) {
        const context = await browser.newContext({ javaScriptEnabled, viewport: { width: 320, height: 800 } });
        await context.route('**/*', route => route.request().url().startsWith(origin) ? route.continue() : route.abort());
        const page = await context.newPage();
        if (javaScriptEnabled) await page.clock.install({ time: new Date() });
        await page.goto(`${origin}/special/many-dates/`);
        expect(await page.getByRole('region', { name: 'About', exact: true }).isVisible()).toBe(true);
        expect(await page.locator('.sheet > *').evaluateAll(elements =>
          elements.slice(0, 3).map(element => element.className),
        )).toEqual(['sheet__head', 'sheet__about', 'sheet__facts']);
        const about = (await page.locator('.sheet__about').boundingBox())!;
        const facts = (await page.locator('.sheet__facts').boundingBox())!;
        expect(about.y + about.height).toBeLessThanOrEqual(facts.y);
        expect(await page.locator('.sheet__facts > .fact').first().innerText()).not.toContain(`${dateText(-2)} · 17:00`);
        expect(await page.locator('[data-sheet-when]').count()).toBe(1);
        expect(await page.locator('[data-sheet-when]').innerText()).toBe(`${dateText(1)} · 17:00–22:00`);
        const calendar = page.locator('[data-calendar-primary]');
        expect(await calendar.count()).toBe(1);
        expect((await calendar.boundingBox())!.height).toBe(32);
        expect(await calendar.evaluate(element => getComputedStyle(element).textTransform)).toBe('none');
        expect(await calendar.getAttribute('href')).toBe(`/special/many-dates/calendar/${day(1)}.ics`);
        const downloaded = page.waitForEvent('download');
        await calendar.focus();
        await page.keyboard.press('Enter');
        const download = await downloaded;
        expect(download.suggestedFilename()).toBe(`many-dates-${day(1)}.ics`);
        const content = readFileSync((await download.path())!, 'utf8');
        expect(content.match(/BEGIN:VEVENT/g)?.length).toBe(1);
        expect(content).not.toContain('RRULE');
        expect(await page.locator('[data-schedule-more] li:visible').count()).toBe(0);
        expect(await page.locator('.sheet__facts').innerText()).toContain('from €23.80');
        const summary = page.locator('[data-schedule-more] > summary');
        await summary.focus();
        await page.keyboard.press('Enter');
        expect(await page.locator('[data-schedule-more] li:visible').count()).toBe(10);
        expect(await page.locator('[data-schedule-more]').innerText()).toContain('Selected dates only');
        expect(await page.locator('[data-schedule-more] li').first().getAttribute('data-occurrence-date')).toBe(day(-2));
        expect(await summary.evaluate(element => document.activeElement === element)).toBe(true);
        expect((await summary.boundingBox())!.height).toBeGreaterThanOrEqual(44);
        if (javaScriptEnabled) {
          await page.clock.setSystemTime(new Date(`${day(4)}T12:00:00Z`));
          await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
          expect(await page.locator('[data-sheet-when]').innerText()).toBe(`${dateText(4)} · 17:00–22:00`);
          await page.clock.setSystemTime(new Date(`${day(4)}T21:00:00Z`));
          await page.clock.fastForward(60_000);
          expect(await page.locator('[data-sheet-when]').innerText()).toBe(`${dateText(5)} · 17:00–22:00`);
          expect(await calendar.getAttribute('href')).toBe(`/special/many-dates/calendar/${day(5)}.ics`);
          expect(await summary.evaluate(element => document.activeElement === element)).toBe(true);
          await calendar.focus();
          await page.clock.setSystemTime(new Date(`${day(8)}T23:30:00Z`));
          await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
          expect(await page.locator('[data-sheet-when]').evaluate(element => document.activeElement === element)).toBe(true);
          expect(await page.locator('[data-sheet-when]').innerText()).toBe('Ended');
          expect(await calendar.isVisible()).toBe(false);
          expect(await page.locator('[data-calendar-date]:visible').count()).toBe(0);
          expect(await page.locator('[data-schedule-more] li:visible').count()).toBe(10);
          await page.clock.setSystemTime(new Date());
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
        expect(await page.locator('[data-sheet-when]').innerText()).toBe('Check source for dates');
        expect(await page.locator('[data-calendar-primary]').count()).toBe(0);
        const sourceSchedule = page.locator('[data-source-schedule] > summary');
        await sourceSchedule.focus();
        await page.keyboard.press('Enter');
        expect(await page.locator('[data-source-schedule]').innerText()).toContain(hoursText);
        await page.goto(`${origin}/special/partial-hours/`);
        expect(await page.locator('.sheet__facts').innerText()).not.toContain('daily');
        expect(await page.locator('[data-sheet-when]').innerText()).toBe(`${dateText(1)} · 11:00–21:00`);
        if (javaScriptEnabled) {
          await page.clock.setSystemTime(new Date(`${day(4)}T12:00:00Z`));
          await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
          expect(await page.locator('[data-sheet-when]').innerText()).toBe(dateText(4));
          await page.clock.setSystemTime(new Date());
        }
        for (const [slug, expected] of [
          ['daily-hours', `${dateText(1)} · 11:00–21:00`],
          ['cancelled', 'Check source for dates'],
          ['postponed', 'Check source for dates'],
          ['rescheduled', `${dateText(1)} · from 17:00`],
          ['date-only', dateText(1)],
          ['exhausted-dates', 'Check source for dates'],
          ['day-30', `${dateText(30)} · from 17:00`],
          ['day-31', 'Check source for dates'],
        ]) {
          await page.goto(`${origin}/special/${slug}/`);
          expect(await page.locator('[data-sheet-when]').innerText()).toBe(expected);
          if (['cancelled', 'postponed', 'exhausted-dates', 'day-31'].includes(slug)) {
            expect(await page.locator('[data-calendar-primary]').count()).toBe(0);
          }
          if (slug === 'date-only') {
            expect(await page.locator('[data-calendar-primary]').textContent()).toBe('Download date reminder (.ics)');
          }
          if (slug === 'daily-hours') {
            await page.locator('[data-schedule-more] > summary').focus();
            await page.keyboard.press('Enter');
            expect(await page.locator('[data-schedule-more]').innerText()).toContain('daily 11:00–21:00');
          }
        }
        await page.goto(`${origin}/special/ended-dates/`);
        expect(await page.locator('meta[name="robots"]').getAttribute('content')).toBe('noindex, follow');
        expect(await page.locator('[data-occasion-actions]').count()).toBe(0);
        expect(await page.locator('[data-sheet-when]').innerText()).toBe('Ended');
        expect(await page.locator('[data-schedule-more] li:visible').count()).toBe(0);
        await page.locator('[data-schedule-more] > summary').focus();
        await page.keyboard.press('Enter');
        expect(await page.locator('[data-schedule-more] li:visible').count()).toBe(8);
        await context.close();
      }
    } finally {
      await browser?.close();
      server.stop(true);
      rmSync(root, { recursive: true, force: true });
    }
  }, 60000,
);
