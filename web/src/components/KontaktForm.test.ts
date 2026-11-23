/**
 * The contact form against a localhost stand-in for the `site-forms` Worker (#32).
 *
 * Builds the real site, serves it under the production hostname and drives
 * Chromium through prefill, inline errors, the unavailable fallback and a
 * successful send. Cloudflare's Turnstile script is replaced by a stub that
 * hands out a token (the real one cannot run off-site); the blocked-script
 * case needs no stub, because every other hostname resolves to nothing.
 *
 * Needs Chrome: CI runners ship it. Elsewhere set CHROME_BIN to any Chromium.
 */
import { expect, test } from 'bun:test';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, type Browser } from 'playwright-core';

const projectRoot = fileURLToPath(new URL('../../', import.meta.url));
const trackerPath = fileURLToPath(new URL('./fixtures/umami-tracker.js', import.meta.url));
// Not the production website, so even a leaked beacon would count nowhere.
const TEST_WEBSITE_ID = '00000000-0000-4000-8000-000000000032';
const SITE_HOST = 'boringhannover.de';
const executablePath = process.env.CHROME_BIN;

// Like the real widget, a reset discards the token and issues a fresh one.
const TURNSTILE_STUB = `let options;
window.turnstile = {
  render(_el, given) { options = given; setTimeout(() => options.callback('stub-token'), 0); return 'stub'; },
  reset() { window.__resets = (window.__resets || 0) + 1; setTimeout(() => options.callback('stub-token'), 0); },
};
document.currentScript.onload?.();`;

interface Submission {
  accept: string | null;
  body: Record<string, string>;
}

async function until(check: () => boolean, what: string, ms = 5000): Promise<void> {
  const deadline = Date.now() + ms;
  while (!check()) {
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${what}`);
    await Bun.sleep(25);
  }
}

function buildSite(root: string): string {
  const data = join(root, 'data');
  mkdirSync(data);
  writeFileSync(
    join(data, 'web_events.json'),
    JSON.stringify({
      meta: { week: 42, year: 2026, updatedAt: 'Kontakt fixture', updatedAtISO: new Date().toISOString() },
      movies: [],
      concerts: [],
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
      env: { ...env, WEB_DATA_ROOT: data, WEB_DATA_MODE: 'production', PUBLIC_UMAMI_WEBSITE_ID: TEST_WEBSITE_ID },
      encoding: 'utf8',
      timeout: 120000,
    },
  );
  if (result.error) throw result.error;
  expect(result.status, result.stdout + result.stderr).toBe(0);
  return outDir;
}

test.skipIf(!executablePath && !process.env.CI)(
  'contact form prefills from the query, maps endpoint errors, falls back to e-mail and records only the kind',
  async () => {
    const submissions: Submission[] = [];
    const answers: Response[] = [];
    const sends: { payload: { name?: string; data?: Record<string, string> } }[] = [];
    let dist = '';
    const server = Bun.serve({
      hostname: '127.0.0.1',
      port: 0,
      async fetch(request) {
        const url = new URL(request.url);
        if (url.pathname === '/_forms/submit' && request.method === 'POST') {
          submissions.push({
            accept: request.headers.get('accept'),
            body: (await request.json()) as Record<string, string>,
          });
          return answers.shift() ?? Response.json({ ok: false, error: 'unavailable' }, { status: 503 });
        }
        if (url.pathname === '/s/t.js') {
          return new Response(readFileSync(trackerPath), { headers: { 'content-type': 'application/javascript' } });
        }
        if (url.pathname === '/s/api/send' && request.method === 'POST') {
          sends.push((await request.json()) as (typeof sends)[number]);
          return Response.json({});
        }
        const file = Bun.file(join(dist, url.pathname.endsWith('/') ? `${url.pathname}index.html` : url.pathname));
        return (await file.exists()) ? new Response(file) : new Response('', { status: 404 });
      },
    });
    const origin = `http://${SITE_HOST}:${server.port}`;
    const root = mkdtempSync(join(tmpdir(), 'kontakt-'));
    let browser: Browser | undefined;
    try {
      dist = buildSite(root);
      browser = await chromium.launch({
        ...(executablePath ? { executablePath } : { channel: 'chrome' }),
        args: [`--host-resolver-rules=MAP ${SITE_HOST} 127.0.0.1, MAP * ~NOTFOUND`, '--no-proxy-server'],
      });

      const context = await browser.newContext({ viewport: { width: 375, height: 800 } });
      await context.route('https://challenges.cloudflare.com/**', route =>
        route.fulfill({ contentType: 'application/javascript', body: TURNSTILE_STUB }),
      );
      const page = await context.newPage();
      await page.goto(`${origin}/kontakt/?art=korrektur&bezug=${encodeURIComponent('Kunst & Kürbis')}&seite=/special/kunst-kuerbis/`);

      expect(await page.locator('#kontakt-about').textContent()).toBe('Kunst & Kürbis');
      expect(await page.locator('#kontakt-about').getAttribute('href')).toBe('/special/kunst-kuerbis/');
      // The site's own header and footer frame the page.
      expect(await page.locator('header').first().getByRole('link', { name: /boring hannover/i }).getAttribute('href')).toBe('/');
      expect(await page.locator('footer').isVisible()).toBe(true);
      // The honeypot is unreachable for people and assistive technology.
      expect(await page.locator('.trap').getAttribute('inert')).not.toBeNull();

      // Empty submit: both required fields are named, focus lands on the first, nothing is sent.
      await page.getByRole('button', { name: 'Send' }).click();
      expect(await page.locator('#email-error').textContent()).toBe('Error: Please enter your email address.');
      expect(await page.locator('#message-error').textContent()).toBe('Error: Please enter your message.');
      expect(await page.locator('#kontakt-status').textContent()).toBe('Please check 2 fields.');
      expect(await page.evaluate(() => document.activeElement?.id)).toBe('f-message');
      expect(submissions).toHaveLength(0);

      await page.getByRole('textbox', { name: 'Email', exact: true }).fill('leser@example.org');
      await page.getByRole('textbox', { name: 'Message', exact: true }).fill('Beginn ist 19 Uhr');
      await page.getByRole('textbox', { name: 'Name optional', exact: true }).fill('Lea');

      // The endpoint's field errors appear under the field and reset the challenge token.
      answers.push(Response.json({ ok: false, error: 'invalid', fields: { email: 'invalid' } }, { status: 422 }));
      await page.getByRole('button', { name: 'Send' }).click();
      await until(() => submissions.length === 1, 'the first submission');
      await page.waitForFunction(() => document.querySelector('#email-error:not([hidden])'));
      expect(await page.locator('#email-error').textContent()).toBe(
        "Error: That doesn't look like a valid email address, e.g. name@example.com.",
      );
      expect(await page.getByRole('textbox', { name: 'Email', exact: true }).getAttribute('aria-invalid')).toBe('true');
      expect(await page.evaluate(() => (window as unknown as { __resets?: number }).__resets)).toBe(1);

      // 503: the e-mail address replaces a dead end and the typed text survives.
      await page.waitForFunction(() => document.querySelector('#kontakt-submit .send__label')?.textContent === 'Send message');
      await page.getByRole('button', { name: 'Send' }).click();
      await until(() => submissions.length === 2, 'the second submission');
      await page.waitForFunction(() => !document.querySelector<HTMLElement>('#kontakt-fallback')!.hidden);
      // The address takes the typed text along, read at click time.
      await page.evaluate(() => {
        const link = document.querySelector<HTMLAnchorElement>('#kontakt-fallback-link')!;
        link.addEventListener('click', event => event.preventDefault(), { once: true });
        link.click();
      });
      expect(await page.locator('#kontakt-fallback-link').getAttribute('href')).toBe(
        'mailto:kontakt@boringhannover.de?subject=Kunst%20%26%20K%C3%BCrbis&body=Beginn%20ist%2019%20Uhr',
      );
      expect(await page.getByRole('textbox', { name: 'Message', exact: true }).inputValue()).toBe('Beginn ist 19 Uhr');

      // Success: confirmation takes focus; the event carries the kind and nothing typed.
      answers.push(Response.json({ ok: true, id: 'abc' }));
      await page.waitForFunction(() => document.querySelector('#kontakt-submit .send__label')?.textContent === 'Send message');
      await page.getByRole('button', { name: 'Send' }).click();
      await until(() => submissions.length === 3, 'the third submission');
      await page.waitForFunction(() => document.activeElement?.id === 'kontakt-sent-title');

      expect(submissions[2]).toEqual({
        accept: expect.stringContaining('application/json'),
        body: {
          kind: 'korrektur',
          email: 'leser@example.org',
          name: 'Lea',
          message: 'Beginn ist 19 Uhr',
          context: 'Kunst & Kürbis',
          page: '/special/kunst-kuerbis/',
          website: '',
          'cf-turnstile-response': 'stub-token',
        },
      });
      await until(() => sends.some(send => send.payload.name === 'contact-sent'), 'the contact-sent event');
      expect(sends.filter(send => send.payload.name === 'contact-sent').map(send => send.payload.data)).toEqual([
        { kind: 'korrektur' },
      ]);
      await context.close();

      // Turnstile blocked or unreachable: the address is offered at once.
      const blocked = await browser.newPage();
      await blocked.goto(`${origin}/kontakt/`);
      await blocked.waitForFunction(() => !document.querySelector<HTMLElement>('#kontakt-fallback')!.hidden);
      expect(await blocked.locator('#kontakt-status').textContent()).toBe("The security check couldn't load.");
      // A filled form never waits on a challenge that cannot come.
      await blocked.getByRole('textbox', { name: 'Email', exact: true }).fill('leser@example.org');
      await blocked.getByRole('textbox', { name: 'Message', exact: true }).fill('Hallo');
      await blocked.getByRole('button', { name: 'Send' }).click();
      expect(await blocked.locator('#kontakt-status').textContent()).toBe("The security check couldn't load.");
      expect(await blocked.locator('#kontakt-fallback').isVisible()).toBe(true);
      expect(submissions).toHaveLength(3);
      await blocked.close();

      // Without JavaScript the form stays out of sight and the address is prominent.
      const noScript = await browser.newContext({ javaScriptEnabled: false });
      const plain = await noScript.newPage();
      await plain.goto(`${origin}/kontakt/`);
      expect(await plain.locator('#kontakt-form').isVisible()).toBe(false);
      // Playwright's text engine skips <noscript>, so address it structurally.
      expect(await plain.locator('noscript p').first().textContent()).toBe('The form needs JavaScript.');
      expect(await plain.locator('noscript p').first().isVisible()).toBe(true);
      expect(await plain.locator('noscript a').getAttribute('href')).toBe('mailto:kontakt@boringhannover.de');
      await noScript.close();
    } finally {
      await browser?.close();
      server.stop(true);
      rmSync(root, { recursive: true, force: true });
    }
  },
  120000,
);
