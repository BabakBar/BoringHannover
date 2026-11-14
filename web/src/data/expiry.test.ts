import { expect, test } from 'bun:test';
import { spawnSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { addDays, berlinClock } from '../utils/occasionStatus';

const web = fileURLToPath(new URL('../../', import.meta.url));
const repo = join(web, '..');
const docker = spawnSync('docker', ['info', '--format', '{{.ServerVersion}}'], { encoding: 'utf8', timeout: 10000 });

test.skipIf(docker.status !== 0 && !process.env.CI)('nginx expires stale occasion artifacts on its clock, across aliases and cache requests (#31)', async () => {
  expect(docker.status, docker.stderr).toBe(0);
  const root = mkdtempSync(join(tmpdir(), 'occasion-expiry-'));
  const data = join(root, 'data');
  const dist = join(root, 'dist');
  const container = `occasion-expiry-${root.split('/').at(-1)!.toLowerCase()}`;
  const image = readFileSync(join(repo, 'Dockerfile.web'), 'utf8').match(/^FROM (nginx:\S+)/m)![1];
  const command = (args: string[]) => spawnSync('docker', args, { encoding: 'utf8', timeout: 30000 });
  try {
    if (command(['image', 'inspect', image]).status !== 0) {
      const pull = command(['pull', image]);
      expect(pull.status, pull.stderr).toBe(0);
    }
    mkdirSync(join(data, 'occasions'), { recursive: true });
    const today = berlinClock(new Date()).date;
    const meta = { week: 45, year: 2026, updatedAt: 'Expiry fixture', updatedAtISO: new Date().toISOString() };
    const occasions = [
      ['transition', today], ['expired', addDays(today, -8)],
      ['spring-dst', '2026-03-21'], ['spring-dst-week', '2026-03-22'],
      ['autumn-dst', '2026-10-17'], ['autumn-dst-week', '2026-10-18'], ['new-year', '2026-12-24'],
    ].map(([slug, endDate]) => ({
      id: `expiry:${slug}`, slug, name: slug, kind: 'festival',
      startDate: endDate, endDate, location: 'Hannover', description: 'Expiry fixture.',
      sourceUrl: 'https://example.com/festival', status: 'happening_now',
      programmeCount: 0, locationCount: 0, preview: [], programmePath: `occasions/${slug}.json`,
    }));
    for (const occasion of occasions) {
      writeFileSync(join(data, occasion.programmePath), JSON.stringify({ meta, occasion, programme: [] }));
    }
    writeFileSync(join(data, 'web_events.json'), JSON.stringify({ meta, movies: [], concerts: [], occasions }));
    const env = { ...process.env };
    for (const key of Object.keys(env)) if (key.startsWith('WEB_DATA_')) delete env[key];
    const build = spawnSync(process.execPath, [join(web, 'node_modules/astro/bin/astro.mjs'), 'build', '--root', web, '--outDir', dist], {
      cwd: root, encoding: 'utf8', timeout: 30000,
      env: { ...env, SITE: 'https://boringhannover.de', TZ: 'Pacific/Kiritimati', WEB_DATA_ROOT: data, WEB_DATA_MODE: 'production' },
    });
    expect(build.status, build.stdout + build.stderr).toBe(0);
    const metadataPath = join(dist, 'occasion-lifecycle.js');
    const metadata = (await import(metadataPath)).default;
    for (const [slug, expected] of [
      ['spring-dst', '2026-03-28T23:00:00Z'],
      ['spring-dst-week', '2026-03-29T22:00:00Z'],
      ['autumn-dst', '2026-10-24T22:00:00Z'],
      ['autumn-dst-week', '2026-10-25T23:00:00Z'],
      ['new-year', '2026-12-31T23:00:00Z'],
    ]) expect(metadata[slug].expiresAt).toBe(Date.parse(expected));
    expect(metadata['spring-dst-week'].expiresAt - metadata['spring-dst-week'].endedAt).toBe(167 * 3600000);
    expect(metadata['autumn-dst-week'].expiresAt - metadata['autumn-dst-week'].endedAt).toBe(169 * 3600000);

    // Leave obsolete files present to model missed rebuilds and orphan aliases.
    const html = join(dist, 'special/transition/index.html');
    for (const slug of ['expired', 'orphan', 'invalid']) {
      mkdirSync(join(dist, 'special', slug), { recursive: true });
      copyFileSync(html, join(dist, 'special', slug, 'index.html'));
    }
    copyFileSync(html, join(dist, 'special/transition.html'));
    writeFileSync(join(dist, 'special/transition/calendar.ics'), 'BEGIN:VCALENDAR\r\nEND:VCALENDAR');
    // Only the test artifact's deadlines are shortened. The server clock stays real.
    const endedAt = Date.now() + 4000;
    const expiresAt = endedAt + 2500;
    metadata.transition = { endedAt, expiresAt };
    metadata.invalid = { endedAt: 0, expiresAt: '99999999999999' };
    writeFileSync(metadataPath, `export default ${JSON.stringify(metadata)};`);
    const mounts = [
      '-v', `${join(repo, 'nginx.conf')}:/etc/nginx/conf.d/default.conf:ro`,
      '-v', `${join(repo, 'nginx/occasion-lifecycle.js')}:/etc/nginx/occasion-lifecycle.js:ro`,
      '-v', `${dist}:/usr/share/nginx/html:ro`,
    ];
    const started = command(['run', '-d', '--name', container, '-p', '127.0.0.1::8080',
      ...mounts, image, 'nginx', '-g', 'load_module modules/ngx_http_js_module.so; daemon off;']);
    expect(started.status, started.stderr).toBe(0);
    const port = command(['port', container, '8080/tcp']);
    const origin = `http://${port.stdout.trim()}`;
    let ready = false;
    for (let attempt = 0; attempt < 40; attempt++) {
      try { ready = (await fetch(`${origin}/health`)).ok; } catch { /* starting */ }
      if (ready) break;
      await Bun.sleep(50);
    }
    expect(ready, command(['logs', container]).stderr).toBe(true);
    const request = (path: string, method = 'GET', headers = {}) => fetch(origin + path, { method, headers, redirect: 'manual' });
    const aliases = ['/special/transition/', '/special/transition', '/special/transition/index.html', '/special/transition.html', '/special/%74ransition/', '/special//transition/'];
    for (const method of ['GET', 'HEAD']) {
      for (const path of ['/special/expired/', '/special/expired', '/special/expired/index.html', '/special/orphan/', '/special/invalid/', '/special/constructor/', '/SPECIAL/transition/', '/special/TRANSITION/', '/occasion-lifecycle.js', '/OCCASION-LIFECYCLE.JS', '/special/transition/calendar.ics', '/special/transition.ics']) {
        const reply = await request(path, method);
        expect(reply.status, `${method} ${path}`).toBe(404);
      }
      for (const path of aliases) {
        const reply = await request(path + '?cache=probe', method);
        expect([200, 301], `${method} ${path}`).toContain(reply.status);
        expect(reply.headers.get('cache-control')).toBe('no-store');
        expect(reply.headers.get('cdn-cache-control')).toBe('no-store');
        expect(reply.headers.get('cloudflare-cdn-cache-control')).toBe('no-store');
        expect(reply.headers.get('x-robots-tag')).toBeNull();
        expect(reply.headers.get('x-content-type-options')).toBe('nosniff');
        if (reply.status === 301) expect(reply.headers.get('location')).toBe('/special/transition/?cache=probe');
        if (method === 'HEAD') expect(await reply.text()).toBe('');
      }
    }
    const active = await request('/special/transition/');
    expect(active.headers.get('content-type')).toContain('text/html');
    const etag = active.headers.get('etag')!;
    const conditional = await request('/special/transition/', 'GET', { 'If-None-Match': etag });
    expect(conditional.status).toBe(304);
    expect(conditional.headers.get('cache-control')).toBe('no-store');
    await Bun.sleep(Math.max(0, endedAt - Date.now()) + 10);
    const retained = await request('/special/transition/');
    expect(retained.status).toBe(200);
    expect(retained.headers.get('x-robots-tag')).toBe('noindex, follow');
    await Bun.sleep(Math.max(0, expiresAt - Date.now()) + 10);
    for (const method of ['GET', 'HEAD']) {
      for (const path of aliases) {
        const reply = await request(path + '?now=0&expires=9999999999999', method, { 'If-None-Match': etag, Range: 'bytes=0-100', 'X-Current-Time': '0' });
        expect(reply.status, `${method} ${path}`).toBe(404);
        expect(reply.headers.get('cache-control')).toBe('no-store');
        expect(reply.headers.get('x-robots-tag')).toBe('noindex, follow');
        if (method === 'HEAD') expect(await reply.text()).toBe('');
      }
    }
    expect((await request('/')).status).toBe(200);
    expect((await request('/special/')).status).toBe(200);
    const css = readFileSync(join(dist, 'index.html'), 'utf8').match(/\/assets\/[^" ]+\.css/)![0];
    const asset = await request(css);
    expect(asset.status).toBe(200);
    expect(asset.headers.get('content-type')).toContain('text/css');
    expect(asset.headers.get('cache-control')).toContain('public');
    expect(asset.headers.get('cache-control')).not.toContain('no-store');
    expect(command(['logs', container]).stderr).not.toContain('[error]');
    for (const broken of [null, 'export default { invalid JavaScript;']) {
      if (broken === null) rmSync(metadataPath);
      else writeFileSync(metadataPath, broken);
      const invalid = command(['run', '--rm', ...mounts, image, 'nginx', '-t', '-g', 'load_module modules/ngx_http_js_module.so;']);
      expect(invalid.status, 'missing or malformed deadline module must refuse startup').not.toBe(0);
    }
  } finally {
    command(['rm', '-f', container]);
    rmSync(root, { recursive: true, force: true });
  }
}, 60000);
