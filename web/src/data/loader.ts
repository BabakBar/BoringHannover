import { readFileSync, readdirSync, realpathSync } from 'node:fs';
import { isAbsolute, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import type { z } from 'zod';
import type { EventData, OccasionProgramme } from './types';
import { eventDataSchema, occasionProgrammeSchema } from './schema';
import { resolveDataConfig, type DataConfig } from './resolve';
import { createProvenance, type Provenance } from './provenance';

export interface Snapshot {
  data: EventData;
  programmes: Map<string, OccasionProgramme>;
  provenance: Provenance;
}

/** Structural equality of parsed JSON values; object key order is irrelevant. */
export function sameJson(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (
    typeof left !== 'object' ||
    typeof right !== 'object' ||
    left === null ||
    right === null ||
    Array.isArray(left) !== Array.isArray(right)
  ) {
    return false;
  }
  if (Array.isArray(left)) {
    const other = right as unknown[];
    return (
      left.length === other.length &&
      left.every((item, index) => sameJson(item, other[index]))
    );
  }
  const a = left as Record<string, unknown>;
  const b = right as Record<string, unknown>;
  const keys = Object.keys(a);
  return (
    keys.length === Object.keys(b).length &&
    keys.every((key) => Object.hasOwn(b, key) && sameJson(a[key], b[key]))
  );
}

export function readSnapshot(config: DataConfig, now = Date.now()): Snapshot {
  const { mode, dataRoot, maxAgeDays } = config;
  const manifestPath = join(dataRoot, 'web_events.json');
  const error = (path: string, reason: string) =>
    new Error(
      `[web-data] mode=${mode} path=${JSON.stringify(path)}: ${reason}`,
    );
  const warn = (path: string, reason: string) =>
    console.warn(error(path, reason).message);
  const problem = (path: string, reason: string) => {
    if (mode === 'production') {
      throw error(path, reason);
    }
    warn(path, reason);
  };
  function read(path: string): string {
    // Checking the real path prevents symlinks from mixing snapshots across roots.
    const target = relative(realpathSync(dataRoot), realpathSync(path));
    if (target === '..' || target.startsWith('../') || isAbsolute(target)) {
      throw error(path, 'path resolves outside data root');
    }
    return readFileSync(path, 'utf8');
  }
  // Returns the raw JSON too: the schema strips unknown keys, but the summary
  // comparison must see every published field, as the Python writer does.
  function parse<T>(
    content: string,
    schema: z.ZodType<T>,
    path: string,
  ): { raw: unknown; data: T } {
    let value: unknown;
    try {
      value = JSON.parse(content);
    } catch {
      throw error(path, 'malformed JSON');
    }
    const result = schema.safeParse(value);
    if (!result.success) {
      const issues = result.error.issues
        .slice(0, 10)
        .map((issue) => `${issue.path.join('.') || '<root>'} (${issue.code})`);
      throw error(path, `schema validation failed: ${issues.join(', ')}`);
    }
    return { raw: value, data: result.data };
  }
  let content: string;
  try {
    content = read(manifestPath);
  } catch (cause) {
    const code = (cause as NodeJS.ErrnoException).code;
    if (!code) {
      throw cause;
    }
    throw error(manifestPath, `cannot read manifest (${code})`);
  }
  const { raw: rawManifest, data } = parse(
    content,
    eventDataSchema,
    manifestPath,
  );
  const rawSummaries = (rawManifest as { occasions: unknown[] }).occasions;
  const timestamp = data.meta.updatedAtISO
    ? Date.parse(data.meta.updatedAtISO)
    : NaN;
  if (!Number.isFinite(timestamp)) {
    problem(manifestPath, 'meta.updatedAtISO is required for freshness');
  } else if (timestamp > now) {
    problem(manifestPath, 'meta.updatedAtISO is in the future');
  } else if (now - timestamp > maxAgeDays * 86400000) {
    problem(manifestPath, `stale meta.updatedAtISO exceeds ${maxAgeDays} days`);
  }

  const programmes = new Map<string, OccasionProgramme>();
  const referenced = new Set<string>();
  const slugs = new Set<string>();
  const ids = new Set<string>();
  const digest = createHash('sha256').update(
    JSON.stringify(['web_events.json', content]),
  );
  const occasions = data.occasions.filter((occasion, index) => {
    const path = join(dataRoot, occasion.programmePath);
    if (
      referenced.has(occasion.programmePath) ||
      slugs.has(occasion.slug) ||
      ids.has(occasion.id)
    ) {
      problem(manifestPath, 'duplicate occasion id, slug, or programmePath');
      return false;
    }
    referenced.add(occasion.programmePath);
    slugs.add(occasion.slug);
    ids.add(occasion.id);
    try {
      const programmeContent = read(path);
      const { raw: rawProgramme, data: programme } = parse(
        programmeContent,
        occasionProgrammeSchema,
        path,
      );
      if (
        programme.occasion.id !== occasion.id ||
        programme.occasion.slug !== occasion.slug ||
        programme.occasion.programmePath !== occasion.programmePath ||
        programme.occasion.startDate !== occasion.startDate ||
        programme.occasion.endDate !== occasion.endDate
      ) {
        throw error(
          path,
          'programme occasion identity or date range does not match manifest',
        );
      }
      // Same rule as the Python writer (publication._programmes): a manifest
      // whose summary differs from the programme's embedded summary is a torn
      // or inconsistent publication, even when identity and dates agree.
      if (
        !sameJson(
          rawSummaries[index],
          (rawProgramme as { occasion: unknown }).occasion,
        )
      ) {
        throw error(path, 'programme occasion summary does not match manifest');
      }
      if (programme.programme.length !== occasion.programmeCount) {
        throw error(
          path,
          `programme has ${programme.programme.length} items but manifest programmeCount is ${occasion.programmeCount}`,
        );
      }
      programmes.set(occasion.programmePath, programme);
      digest.update(JSON.stringify([occasion.programmePath, programmeContent]));
      return true;
    } catch (cause) {
      const code = (cause as NodeJS.ErrnoException).code;
      const failure = code
        ? error(path, `cannot read programme (${code})`)
        : cause;
      if (mode === 'production') {
        throw failure;
      }
      console.warn((failure as Error).message);
      return false;
    }
  });
  let orphanCount = 0;
  const occasionDirectory = join(dataRoot, 'occasions');
  try {
    orphanCount = readdirSync(occasionDirectory).filter(
      (name) => name.endsWith('.json') && !referenced.has(`occasions/${name}`),
    ).length;
  } catch (cause) {
    const code = (cause as NodeJS.ErrnoException).code;
    if (code !== 'ENOENT') {
      problem(
        occasionDirectory,
        `cannot list programmes (${code ?? 'unknown error'})`,
      );
    }
  }
  if (orphanCount) {
    warn(occasionDirectory, `${orphanCount} orphan programme files`);
  }
  const acceptedData = { ...data, occasions };
  return {
    data: acceptedData,
    programmes,
    provenance: createProvenance(acceptedData, {
      mode,
      dataRoot,
      orphanCount,
      revision: digest.digest('hex'),
    }),
  };
}

// Astro bundles server modules into dist; inject the source root from the config
// so import.meta.url relocation cannot change which output directory is selected.
const projectRoot =
  import.meta.env?.WEB_PROJECT_ROOT ??
  fileURLToPath(new URL('../../', import.meta.url));
let snapshot: Snapshot | undefined;
function loadSnapshot(): Snapshot {
  const dev = import.meta.env?.DEV ?? false;
  if (!snapshot || dev) {
    const config = resolveDataConfig(
      {
        DEV: dev,
        WEB_DATA_MODE:
          process.env.WEB_DATA_MODE ?? import.meta.env?.WEB_DATA_MODE,
        WEB_DATA_ROOT:
          process.env.WEB_DATA_ROOT ?? import.meta.env?.WEB_DATA_ROOT,
        WEB_DATA_MAX_AGE_DAYS:
          process.env.WEB_DATA_MAX_AGE_DAYS ??
          import.meta.env?.WEB_DATA_MAX_AGE_DAYS,
      },
      projectRoot,
    );
    const next = readSnapshot(config);
    if (
      !snapshot ||
      next.provenance.revision !== snapshot.provenance.revision
    ) {
      console.info(`[web-data] ${JSON.stringify(next.provenance)}`);
    }
    snapshot = next;
  }
  return snapshot;
}

export function loadEventData(): EventData {
  return loadSnapshot().data;
}
export function loadOccasionProgramme(
  programmePath: string,
): OccasionProgramme | null {
  return loadSnapshot().programmes.get(programmePath) ?? null;
}
export function getDataProvenance(): Provenance {
  return loadSnapshot().provenance;
}
