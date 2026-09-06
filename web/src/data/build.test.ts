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
