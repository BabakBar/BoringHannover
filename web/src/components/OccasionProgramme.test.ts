import { afterAll, beforeAll, describe, expect, test } from 'bun:test';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, type Browser } from 'playwright-core';
import { addDays, berlinClock } from '../utils/occasionStatus';

const projectRoot = fileURLToPath(new URL('../../', import.meta.url));
const executablePath = process.env.CHROME_BIN;
const today = berlinClock(new Date()).date;
const weekday = new Date(`${today}T12:00:00Z`).getUTCDay();
const saturday = addDays(today, (6 - weekday + 7) % 7);
const friday = addDays(saturday, -1);
const sunday = addDays(saturday, 1);
const monday = addDays(saturday, 2);
function midnightAfter(date: string, minutes: number): Date {
  const utc = new Date(`${date}T00:00:00Z`);
  return new Date(utc.getTime() + (minutes - berlinClock(utc).minutes) * 60000);
}

describe.skipIf(!executablePath && !process.env.CI)('occasion programme', () => {
  let root: string;
  let browser: Browser | undefined;
  let server: ReturnType<typeof Bun.serve> | undefined;
  let origin: string;

  beforeAll(async () => {
    root = mkdtempSync(join(tmpdir(), 'occasion-programme-'));
    const data = join(root, 'data');
    const dist = join(root, 'dist');
    mkdirSync(join(data, 'occasions'), { recursive: true });
    const event = (key: string, dateISO: string, extra: Record<string, unknown> = {}) => ({
      title: key, dateISO, date: dateISO, day: '', time: '20:00',
      timeConfidence: 'confirmed', venue: 'Main stage', programmeCategory: 'Music',
      url: `https://venue.test/${key}`, ...extra,
    });
    const programme = [
      event('friday-one', friday, { programmeCategory: 'Talk', venue: 'Second stage' }),
      event('friday-two', friday, { programmeCategory: 'Talk', venue: 'Second stage' }),
      ...Array.from({ length: 25 }, (_, index) => event(
        `saturday-${index + 1}`, saturday,
        { venue: index % 2 ? 'Second stage' : 'Main stage' },
      )),
      event('fallback-time', saturday, { timeConfidence: 'fallback' }),
      event('sunday-one', sunday, { programmeCategory: 'Talk' }),
    ];
    const occasion = {
      id: 'programme:fixture', slug: 'programme-fixture', name: 'Programme fixture',
      kind: 'festival', startDate: friday, endDate: sunday,
      location: 'Hannover', description: 'See the source for details.',
      sourceUrl: 'https://venue.test/festival', status: 'happening_now',
      programmeCount: programme.length, locationCount: 2,
      programmePath: 'occasions/programme-fixture.json', preview: [],
      scheduleConfidence: 'continuous',
    };
    const meta = { week: 31, year: 2026, updatedAt: 'Programme fixture', updatedAtISO: new Date().toISOString() };
    writeFileSync(join(data, occasion.programmePath), JSON.stringify({ meta, occasion, programme }));
    writeFileSync(join(data, 'web_events.json'), JSON.stringify({ meta, movies: [], concerts: [], occasions: [occasion] }));
    const env = { ...process.env };
    for (const key of Object.keys(env)) {
      if (key.startsWith('WEB_DATA_') || key.startsWith('PUBLIC_UMAMI_')) delete env[key];
    }
    const build = spawnSync(process.execPath, [
      join(projectRoot, 'node_modules/astro/bin/astro.mjs'), 'build', '--root', projectRoot, '--outDir', dist,
    ], {
      cwd: root, encoding: 'utf8', timeout: 30000,
      env: { ...env, WEB_DATA_ROOT: data, WEB_DATA_MODE: 'fixture', PUBLIC_UMAMI_WEBSITE_ID: '00000000-0000-4000-8000-000000000054' },
    });
    expect(build.status, build.stdout + build.stderr).toBe(0);
    expect(readFileSync(join(dist, 'special/programme-fixture/index.html'), 'utf8')).not.toContain('23cf1ce2-3635-4e97-aab9-6ccd0467f839');
    server = Bun.serve({ hostname: '127.0.0.1', port: 0, async fetch(request) {
      const path = new URL(request.url).pathname;
      const file = Bun.file(join(dist, path.endsWith('/') ? `${path}index.html` : path));
      return await file.exists() ? new Response(file) : new Response('', { status: 404 });
    } });
    origin = `http://127.0.0.1:${server.port}`;
    browser = await chromium.launch(executablePath ? { executablePath } : { channel: 'chrome' });
  });

  afterAll(async () => {
    await browser?.close();
    server?.stop(true);
    if (root) rmSync(root, { recursive: true, force: true });
  });

  test('filters follow Berlin dates and reliable times in different visitor timezones (#54)', async () => {
    for (const timezoneId of ['America/Los_Angeles', 'Asia/Tokyo']) {
      const context = await browser!.newContext({ timezoneId });
      try {
        await context.route('**/*', route => route.request().url().startsWith(`${origin}/`) ? route.continue() : route.abort());
        const page = await context.newPage();
        const errors: string[] = [];
        page.on('pageerror', error => errors.push(error.message));
        // Saturday in Berlin, still Friday in California.
        await page.clock.install({ time: midnightAfter(saturday, 30) });
        await page.goto(`${origin}/special/programme-fixture/`);
        const visible = page.locator('[data-programme-item]:visible');
        const count = page.locator('#programme-result-count');
        const today = page.locator('[data-mode-filter="today"]');
        expect(await today.getAttribute('aria-pressed')).toBe('true');
        expect(await count.innerText()).toBe('12 of 26 events');
        expect(await count.evaluate(element => new Promise<number>(resolve => {
          let changes = 0;
          const observer = new MutationObserver(records => { changes += records.length; });
          observer.observe(element, { childList: true, characterData: true, subtree: true });
          document.dispatchEvent(new Event('visibilitychange'));
          queueMicrotask(() => { observer.disconnect(); resolve(changes); });
        }))).toBe(0);
        expect(await visible.evaluateAll((items, date) => items.every(item => item.getAttribute('data-date') === date), saturday)).toBe(true);
        await page.locator('[data-mode-filter="tonight"]').click();
        expect(await count.innerText()).toBe('12 of 25 events');
        await page.locator('#programme-more').click();
        await page.locator('#programme-more').click();
        expect(await visible.count()).toBe(25);
        expect(await page.getByRole('heading', { name: 'fallback-time', exact: true }).isVisible()).toBe(false);

        await page.locator(`[data-date-filter="${friday}"]`).click();
        expect(await visible.count()).toBe(2);
        expect(await page.locator('[data-mode-filter="all"]').getAttribute('aria-pressed')).toBe('true');
        await page.locator('[data-mode-filter="all"]').click();
        await page.locator('[data-category-filter="Talk"]').click();
        await page.locator('#programme-venue-filter').selectOption('Main stage');
        expect(await visible.count()).toBe(1);
        expect(await visible.innerText()).toContain('sunday-one');
        await page.locator(`[data-date-filter="${friday}"]`).click();
        expect(await visible.count()).toBe(0);
        expect(await page.locator('#programme-empty').isVisible()).toBe(true);

        await page.locator('[data-category-filter="all"]').click();
        await page.locator('#programme-venue-filter').selectOption('all');
        await today.click();
        await today.focus();
        // The open tab refreshes on its minute timer and keeps control focus.
        await page.clock.setSystemTime(midnightAfter(sunday, 5));
        await page.clock.fastForward(60000);
        expect(await count.innerText()).toBe('1 event');
        expect(await visible.innerText()).toContain('sunday-one');
        expect(await today.evaluate(element => document.activeElement === element)).toBe(true);
        const weekend = page.locator('[data-mode-filter="weekend"]');
        await weekend.click();
        expect(await visible.count()).toBe(1);
        // On Monday in Berlin, Weekend advances to the next Saturday/Sunday.
        await page.clock.setSystemTime(midnightAfter(monday, 30));
        await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
        expect(await visible.count()).toBe(0);
        expect(await weekend.evaluate(element => document.activeElement === element)).toBe(true);
        expect(errors).toEqual([]);
      } finally {
        await context.close();
      }
    }
  }, 60000);

  for (const refresh of ['timer', 'visibilitychange'] as const) {
    test(`More button keeps a meaningful focus target across ${refresh} refresh`, async () => {
      const context = await browser!.newContext();
      try {
        await context.route('**/*', route => route.request().url().startsWith(`${origin}/`) ? route.continue() : route.abort());
        const page = await context.newPage();
        await page.clock.install({ time: new Date(`${saturday}T12:00:00Z`) });
        await page.goto(`${origin}/special/programme-fixture/`);
        const more = page.locator('#programme-more');
        const count = page.locator('#programme-result-count');
        const refreshPage = async () => {
          if (refresh === 'timer') await page.clock.fastForward(60000);
          else await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
        };

        await more.focus();
        await refreshPage();
        expect(await more.isVisible()).toBe(true);
        expect(await more.evaluate(element => document.activeElement === element)).toBe(true);

        // Berlin midnight reduces today's results from 26 to one. The focused
        // pagination button disappears even though it is not a programme item.
        await page.clock.setSystemTime(midnightAfter(sunday, 5));
        await refreshPage();
        expect(await count.innerText()).toBe('1 event');
        expect(await more.isVisible()).toBe(false);
        expect(await count.evaluate(element => document.activeElement === element)).toBe(true);

        // A refresh with focus elsewhere must not move it into the programme.
        await page.clock.setSystemTime(new Date(`${saturday}T12:00:00Z`));
        await page.reload();
        const today = page.locator('[data-mode-filter="today"]');
        await today.focus();
        await page.clock.setSystemTime(midnightAfter(sunday, 5));
        await refreshPage();
        expect(await more.isVisible()).toBe(false);
        expect(await today.evaluate(element => document.activeElement === element)).toBe(true);
      } finally {
        await context.close();
      }
    }, 60000);
  }

  test('controls need JS and pagination keeps keyboard focus in newly revealed content (#37)', async () => {
    for (const javaScriptEnabled of [false, true]) {
      const context = await browser!.newContext({ javaScriptEnabled });
      try {
        await context.route('**/*', route => route.request().url().startsWith(`${origin}/`) ? route.continue() : route.abort());
        const page = await context.newPage();
        if (javaScriptEnabled) await page.clock.install({ time: new Date(`${saturday}T12:00:00Z`) });
        await page.goto(`${origin}/special/programme-fixture/`);
        const visible = page.locator('[data-programme-item]:visible');
        const more = page.locator('#programme-more');
        expect(await page.getByText('Programme dates and times use Berlin time.', { exact: true }).isVisible()).toBe(true);
        if (!javaScriptEnabled) {
          expect(await visible.count()).toBe(29);
          expect(await page.locator('[data-mode-filter]:visible, [data-date-filter]:visible, [data-category-filter]:visible, #programme-venue-filter:visible').count()).toBe(0);
          expect(await more.isVisible()).toBe(false);
          expect(await page.locator('[data-programme-item] a').first().getAttribute('href')).toBe('https://venue.test/friday-one');
          continue;
        }
        expect(await visible.count()).toBe(12);
        for (const name of ['Quick time filters', 'Choose a date', 'Programme categories']) {
          expect(await page.getByRole('group', { name, exact: true }).isVisible()).toBe(true);
        }
        expect(await page.locator('[data-mode-filter], [data-category-filter]').evaluateAll(
          controls => controls.every(control => control.getBoundingClientRect().height >= 44),
        )).toBe(true);
        await more.focus();
        await page.keyboard.press('Enter');
        expect(await visible.count()).toBe(24);
        const firstNew = page.getByRole('heading', { name: 'saturday-13', exact: true });
        expect(await firstNew.evaluate(element => document.activeElement === element)).toBe(true);
        expect(await firstNew.evaluate(element => getComputedStyle(element).outlineStyle)).not.toBe('none');
        await page.keyboard.press('Tab');
        expect(await page.evaluate(() => (document.activeElement as HTMLAnchorElement).getAttribute('href'))).toBe('https://venue.test/saturday-13');
        await more.focus();
        await page.keyboard.press('Space');
        expect(await visible.count()).toBe(26);
        expect(await more.isVisible()).toBe(false);
        expect(await page.getByRole('heading', { name: 'saturday-25', exact: true }).evaluate(element => document.activeElement === element)).toBe(true);

        // A passive midnight refresh must also avoid dropping focus to body.
        await page.clock.setSystemTime(midnightAfter(sunday, 5));
        await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
        expect(await visible.count()).toBe(1);
        expect(await page.locator('#programme-result-count').evaluate(element => document.activeElement === element)).toBe(true);
      } finally {
        await context.close();
      }
    }
  }, 60000);
});
