import { afterEach, expect, test } from 'bun:test';
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  rmSync,
  symlinkSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { resolveDataConfig } from './resolve';
import { readSnapshot } from './loader';
import { publicProvenance } from './provenance';
import type { EventData } from './types';

const roots: string[] = [];
const now = Date.parse('2026-09-06T12:00:00Z');
const feed = (): EventData => ({
  meta: {
    week: 36,
    year: 2026,
    updatedAt: 'Fri 04 Sep',
    updatedAtISO: '2026-09-04T11:00:00+02:00',
  },
  movies: [],
  concerts: [],
  occasions: [],
});
function setup(mode = 'production') {
  const root = mkdtempSync(join(tmpdir(), 'handoff-'));
  roots.push(root);
  mkdirSync(join(root, 'output', 'occasions'), { recursive: true });
  const config = resolveDataConfig({ WEB_DATA_MODE: mode }, root);
  return {
    root,
    config,
    write: (data: unknown) =>
      writeFileSync(
        join(config.dataRoot, 'web_events.json'),
        JSON.stringify(data),
      ),
  };
}
const occasion = {
  id: 'source:festival',
  slug: 'festival',
  name: 'Festival',
  kind: 'festival',
  startDate: '2026-09-01',
  endDate: '2026-09-10',
  location: 'Hannover',
  description: '',
  sourceUrl: 'https://example.com',
  status: 'happening_now',
  programmeCount: 0,
  locationCount: 0,
  programmePath: 'occasions/festival.json',
  preview: [],
};
afterEach(() => {
  for (const root of roots.splice(0))
    rmSync(root, { recursive: true, force: true });
});
test('resolution is anchored; explicit absolute and relative roots win', () => {
  expect(resolveDataConfig({}, '/project/web').dataRoot).toBe(
    '/project/web/output',
  );
  expect(
    resolveDataConfig({ WEB_DATA_ROOT: '../fixture' }, '/project/web').dataRoot,
  ).toBe('/project/fixture');
  expect(
    resolveDataConfig({ WEB_DATA_ROOT: '/fixture' }, '/project/web').dataRoot,
  ).toBe('/fixture');
  expect(resolveDataConfig({ DEV: true }, '/project/web').mode).toBe('mock');
});
test('invalid configuration fails closed', () => {
  for (const env of [
    { WEB_DATA_MODE: 'prod' },
    { WEB_DATA_ROOT: '' },
    ...['0', '-1', 'NaN', 'Infinity', ''].map((WEB_DATA_MAX_AGE_DAYS) => ({
      WEB_DATA_MAX_AGE_DAYS,
    })),
  ]) {
    expect(() => resolveDataConfig(env, '/project/web')).toThrow();
  }
});
test('never selects decoy parent output', () => {
  const { root, config, write } = setup();
  write(feed());
  const nested = join(root, 'web');
  mkdirSync(join(nested, 'output'), { recursive: true });
  writeFileSync(
    join(nested, 'output/web_events.json'),
    JSON.stringify({ ...feed(), meta: { ...feed().meta, week: 37 } }),
  );
  expect(readSnapshot(resolveDataConfig({}, nested), now).data.meta.week).toBe(
    37,
  );
  expect(readSnapshot(config, now).data.meta.week).toBe(36);
});
test('missing production and fixture data cannot use mock; mock mode records fallback', () => {
  for (const mode of ['production', 'fixture']) {
    const { config } = setup(mode);
    expect(() => readSnapshot(config, now)).toThrow(`${mode}`);
  }
  const { config } = setup('mock');
  expect(readSnapshot(config, now).provenance.source).toBe('mock');
});
test('malformed JSON and invalid schema throw without payload in every mode', () => {
  for (const mode of ['production', 'mock', 'fixture']) {
    const { config, write } = setup(mode);
    writeFileSync(join(config.dataRoot, 'web_events.json'), '{SECRET');
    expect(() => readSnapshot(config, now)).toThrow('malformed JSON');
    write({ ...feed(), movies: 'SECRET' });
    try {
      readSnapshot(config, now);
      throw new Error('accepted');
    } catch (error) {
      expect(String(error)).toContain('movies');
      expect(String(error)).not.toContain('SECRET');
    }
  }
});
test('freshness requires timestamp and respects exact budget', () => {
  const { config, write } = setup();
  for (const updatedAtISO of [
    undefined,
    'invalid',
    '2026-09-07T00:00:00Z',
    '2026-08-01T00:00:00Z',
  ]) {
    write({ ...feed(), meta: { ...feed().meta, updatedAtISO } });
    expect(() => readSnapshot(config, now)).toThrow();
  }
  write({
    ...feed(),
    meta: {
      ...feed().meta,
      updatedAtISO: new Date(now - 10 * 86400000).toISOString(),
    },
  });
  expect(readSnapshot(config, now).data.meta.week).toBe(36);
  expect(() => readSnapshot(config, now + 1)).toThrow('stale');
  expect(
    readSnapshot({ ...config, maxAgeDays: 11 }, now + 1).data.meta.week,
  ).toBe(36);
});
test('programme validation is eager; nonproduction skips broken occasions', () => {
  for (const mode of ['production', 'fixture', 'mock']) {
    const { config, write } = setup(mode);
    write({ ...feed(), occasions: [occasion] });
    if (mode === 'production')
      expect(() => readSnapshot(config, now)).toThrow('festival.json');
    else expect(readSnapshot(config, now).data.occasions).toEqual([]);
    writeFileSync(
      join(config.dataRoot, occasion.programmePath),
      JSON.stringify({ meta: { updatedAt: 'today' }, occasion, programme: [] }),
    );
    expect(readSnapshot(config, now).programmes.size).toBe(1);
    writeFileSync(join(config.dataRoot, occasion.programmePath), '{}');
    if (mode === 'production')
      expect(() => readSnapshot(config, now)).toThrow('validation');
    else expect(readSnapshot(config, now).data.occasions).toEqual([]);
  }
});
test('rejects path traversal, mismatched identity, and symlink escapes', () => {
  const { config, root, write } = setup();
  write({
    ...feed(),
    occasions: [{ ...occasion, programmePath: '../secret.json' }],
  });
  expect(() => readSnapshot(config, now)).toThrow('programmePath');
  write({ ...feed(), occasions: [occasion] });
  const external = join(root, 'external.json');
  writeFileSync(
    external,
    JSON.stringify({ meta: { updatedAt: 'today' }, occasion, programme: [] }),
  );
  symlinkSync(external, join(config.dataRoot, occasion.programmePath));
  expect(() => readSnapshot(config, now)).toThrow('outside');
});
test('orphan files are counted without deletion; public provenance excludes paths', () => {
  const { config, write } = setup();
  write(feed());
  writeFileSync(join(config.dataRoot, 'occasions/orphan.json'), '{}');
  const snapshot = readSnapshot(config, now);
  expect(snapshot.provenance.orphanCount).toBe(1);
  expect(snapshot.provenance.revision).toMatch(/^[a-f0-9]{64}$/);
  expect(publicProvenance(snapshot.provenance)).not.toHaveProperty('dataRoot');
  expect(JSON.stringify(publicProvenance(snapshot.provenance))).not.toContain(
    config.dataRoot,
  );
  expect(readSnapshot(config, now).provenance.revision).toBe(
    snapshot.provenance.revision,
  );
  write({
    ...feed(),
    concerts: [
      { title: 'Changed', date: '06 Sep', day: 'Sun', venue: 'Venue' },
    ],
  });
  expect(readSnapshot(config, now).provenance.revision).not.toBe(
    snapshot.provenance.revision,
  );
});

test('programme identity and duplicate route checks fail closed', () => {
  const { config, write } = setup();
  write({ ...feed(), occasions: [occasion] });
  writeFileSync(
    join(config.dataRoot, occasion.programmePath),
    JSON.stringify({
      meta: { updatedAt: 'today' },
      occasion: { ...occasion, id: 'wrong' },
      programme: [],
    }),
  );
  expect(() => readSnapshot(config, now)).toThrow('identity');
  writeFileSync(
    join(config.dataRoot, occasion.programmePath),
    JSON.stringify({ meta: { updatedAt: 'today' }, occasion, programme: [] }),
  );
  const revision = readSnapshot(config, now).provenance.revision;
  writeFileSync(
    join(config.dataRoot, occasion.programmePath),
    JSON.stringify({ meta: { updatedAt: 'changed' }, occasion, programme: [] }),
  );
  expect(readSnapshot(config, now).provenance.revision).not.toBe(revision);
  write({ ...feed(), occasions: [occasion, occasion] });
  expect(() => readSnapshot(config, now)).toThrow('duplicate');
});
test('nonproduction allows stale files without switching to mock', () => {
  for (const mode of ['fixture', 'mock']) {
    const { config, write } = setup(mode);
    write({
      ...feed(),
      meta: { ...feed().meta, updatedAtISO: '2020-01-01T00:00:00Z' },
    });
    expect(readSnapshot(config, now).provenance.source).toBe('file');
  }
});
