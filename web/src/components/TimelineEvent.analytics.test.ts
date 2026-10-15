/**
 * Radar destination clicks reach a real Umami collector exactly once (#76).
 *
 * Builds the homepage from fixture data with an isolated website ID, serves
 * it from localhost under the production hostname (the tracker only collects
 * on its allow-listed domains) and drives Chromium against it. The tracker is
 * Umami's own script, byte-for-byte as https://boringhannover.de/s/t.js
 * served it on 15 Oct 2026. Every other hostname resolves to nothing, so no
 * request can reach production.
 *
 * Needs Chrome: CI runners ship it. Elsewhere set CHROME_BIN to any Chromium.
 */
import { expect, test } from 'bun:test';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, type Browser, type BrowserContext, type Page } from 'playwright-core';

const projectRoot = fileURLToPath(new URL('../../', import.meta.url));
const trackerPath = fileURLToPath(new URL('./fixtures/umami-tracker.js', import.meta.url));
const TRACKER_SHA256 = '654f12c7548be726eba5b71d5ef8bffc2a41a39a0053e2a49a847869ccd7ac3f';
// Not the production website, so even a leaked beacon would count nowhere.
const TEST_WEBSITE_ID = '00000000-0000-4000-8000-000000000076';
const SITE_HOST = 'boringhannover.de';
const DESTINATION_HOST = 'venue.test';
const executablePath = process.env.CHROME_BIN;

interface Send {
  type: string;
  payload: { website?: string; hostname?: string; name?: string; data?: Record<string, string> };
}

async function until(check: () => boolean, what: string, ms = 5000): Promise<void> {
  const deadline = Date.now() + ms;
  while (!check()) {
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${what}`);
    await Bun.sleep(25);
  }
}

function buildSite(root: string, destination: string): string {
  const today = new Date();
  const tomorrow = new Date(today.getTime() + 86400000).toISOString().slice(0, 10);
  const concert = (title: string, url: string | null, eventType?: string) => ({
    title,
    date: '16 Okt',
    dateISO: tomorrow,
    day: 'Fr',
    time: '20:00',
    venue: 'Béi Chéz Heinz',
    url,
    ...(eventType ? { eventType } : {}),
  });
  const data = join(root, 'data');
  mkdirSync(data);
  writeFileSync(
    join(data, 'web_events.json'),
    JSON.stringify({
      meta: { week: 42, year: 2026, updatedAt: 'Analytics fixture', updatedAtISO: today.toISOString() },
      movies: [],
      concerts: [
        // Source titles are untrusted text and keep their German names.
        concert('Fräulein "Wunder" & Co', `${destination}/tickets?ref=list`, 'concert'),
        concert('Untyped Night', `${destination}/untyped`),
        concert('Missing Link Night', null, 'concert'),
        concert('Rejected Link Night', 'javascript:alert(1)', 'concert'),
      ],
      occasions: [],
    }),
  );
  const env = { ...process.env };
  for (const name of Object.keys(env)) {
    if (name.startsWith('WEB_DATA_') || name.startsWith('PUBLIC_UMAMI_')) delete env[name];
  }
  const outDir = join(root, 'dist');
  const result = spawnSync(
    process.execPath,
    [join(projectRoot, 'node_modules/astro/bin/astro.mjs'), 'build', '--root', projectRoot, '--outDir', outDir],
    {
      cwd: root,
      env: {
        ...env,
        WEB_DATA_ROOT: data,
        WEB_DATA_MODE: 'production',
        PUBLIC_UMAMI_WEBSITE_ID: TEST_WEBSITE_ID,
      },
      encoding: 'utf8',
      timeout: 120000,
    },
  );
  if (result.error) throw result.error;
  expect(result.status, result.stdout + result.stderr).toBe(0);
  return outDir;
}

test.skipIf(!executablePath && !process.env.CI)(
  'Radar links record one event-click per activation, never for a missing destination or an opted-out browser',
  async () => {
    const tracker = readFileSync(trackerPath);
    expect(createHash('sha256').update(tracker).digest('hex')).toBe(TRACKER_SHA256);

    const sends: Send[] = [];
    const requests: string[] = [];
    let dist = '';
    const server = Bun.serve({
      hostname: '127.0.0.1',
      port: 0,
      async fetch(request) {
        const url = new URL(request.url);
        requests.push(`${request.method} ${url.hostname}${url.pathname}`);
        if (url.hostname === DESTINATION_HOST) {
          return new Response('<title>Official destination</title>', {
            headers: { 'content-type': 'text/html' },
          });
        }
        if (url.pathname === '/s/t.js') {
          return new Response(tracker, { headers: { 'content-type': 'application/javascript' } });
        }
        if (url.pathname === '/s/api/send' && request.method === 'POST') {
          sends.push((await request.json()) as Send);
          return Response.json({});
        }
        const path = join(dist, url.pathname.endsWith('/') ? `${url.pathname}index.html` : url.pathname);
        const file = Bun.file(path);
        return (await file.exists()) ? new Response(file) : new Response('', { status: 404 });
      },
    });
    const origin = `http://${SITE_HOST}:${server.port}`;
    const destination = `http://${DESTINATION_HOST}:${server.port}`;
    const root = mkdtempSync(join(tmpdir(), 'radar-analytics-'));
    let browser: Browser | undefined;
    try {
      dist = buildSite(root, destination);
      const html = readFileSync(join(dist, 'index.html'), 'utf8');
      expect(html).toContain(`data-website-id="${TEST_WEBSITE_ID}"`);
      expect(html).not.toContain('23cf1ce2-3635-4e97-aab9-6ccd0467f839');

      browser = await chromium.launch({
        ...(executablePath ? { executablePath } : { channel: 'chrome' }),
        args: [
          `--host-resolver-rules=MAP ${SITE_HOST} 127.0.0.1, MAP ${DESTINATION_HOST} 127.0.0.1, MAP * ~NOTFOUND`,
          '--no-proxy-server',
        ],
      });

      const clicks = () => sends.filter(send => send.payload.name === 'event-click');
      const pageviews = () => sends.filter(send => send.type === 'event' && !send.payload.name);
      const open = async (context: BrowserContext): Promise<Page> => {
        const page = await context.newPage();
        await page.goto(`${origin}/`);
        return page;
      };
      const activate = async (page: Page, title: string, how: 'mouse' | 'enter') => {
        const link = page.getByRole('link', { name: new RegExp(title) });
        const popup = page.waitForEvent('popup');
        if (how === 'mouse') await link.click();
        else {
          await link.focus();
          await page.keyboard.press('Enter');
        }
        const opened = await popup;
        await opened.waitForLoadState();
        return opened;
      };

      // Mouse and Enter each record one event and still open the destination
      // natively in a new tab, leaving the list and its focus in place.
      const context = await browser.newContext();
      const page = await open(context);
      await until(() => pageviews().length === 1, 'the pageview');

      const byMouse = await activate(page, 'Fräulein', 'mouse');
      expect(byMouse.url()).toBe(`${destination}/tickets?ref=list`);
      await until(() => clicks().length === 1, 'the mouse event-click');

      const byEnter = await activate(page, 'Fräulein', 'enter');
      expect(byEnter.url()).toBe(`${destination}/tickets?ref=list`);
      await until(() => clicks().length === 2, 'the Enter event-click');
      expect(page.url()).toBe(`${origin}/`);
      expect(await page.evaluate(() => document.activeElement?.textContent)).toContain('Fräulein');

      await activate(page, 'Untyped Night', 'mouse');
      await until(() => clicks().length === 3, 'the untyped event-click');

      // Rejected and missing URLs are '#': no official destination, no event.
      for (const title of ['Missing Link Night', 'Rejected Link Night']) {
        const link = page.getByRole('link', { name: new RegExp(title) });
        expect(await link.getAttribute('href')).toBe('#');
        await activate(page, title, 'mouse');
      }
      await Bun.sleep(1000);

      expect(clicks().map(send => send.payload.data)).toEqual([
        { title: 'Fräulein "Wunder" & Co', venue: 'Béi Chéz Heinz', type: 'concert' },
        { title: 'Fräulein "Wunder" & Co', venue: 'Béi Chéz Heinz', type: 'concert' },
        // A missing property stays absent.
        { title: 'Untyped Night', venue: 'Béi Chéz Heinz' },
      ]);
      for (const send of sends) {
        expect(send.payload.website).toBe(TEST_WEBSITE_ID);
        expect(send.payload.hostname).toBe(SITE_HOST);
      }
      await context.close();

      // Without JavaScript the link is still an ordinary new-tab link.
      const noScript = await browser.newContext({ javaScriptEnabled: false });
      const plain = await open(noScript);
      const native = await activate(plain, 'Fräulein', 'mouse');
      expect(native.url()).toBe(`${destination}/tickets?ref=list`);
      await noScript.close();

      // The owner opt-out: the tracker loads but sends nothing at all.
      sends.length = 0;
      requests.length = 0;
      const optedOut = await browser.newContext();
      await optedOut.addInitScript(() => localStorage.setItem('umami.disabled', '1'));
      const quiet = await open(optedOut);
      await until(() => requests.includes(`GET ${SITE_HOST}/s/t.js`), 'the tracker');
      expect(await quiet.evaluate(() => typeof (window as { umami?: unknown }).umami)).toBe('object');
      await activate(quiet, 'Fräulein', 'mouse');
      await activate(quiet, 'Fräulein', 'enter');
      await optedOut.close();
      await Bun.sleep(1000);
      expect(sends).toEqual([]);
      expect(requests.filter(request => request.includes('/s/api/send'))).toEqual([]);
    } finally {
      await browser?.close();
      server.stop(true);
      rmSync(root, { recursive: true, force: true });
    }
  },
  180000,
);
