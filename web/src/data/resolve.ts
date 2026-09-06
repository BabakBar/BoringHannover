import { isAbsolute, resolve } from 'node:path';

export type DataMode = 'production' | 'mock' | 'fixture';
export interface DataConfig {
  mode: DataMode;
  dataRoot: string;
  maxAgeDays: number;
}
interface DataEnv {
  WEB_DATA_MODE?: string;
  WEB_DATA_ROOT?: string;
  WEB_DATA_MAX_AGE_DAYS?: string;
  DEV?: boolean;
}

export function resolveDataConfig(
  env: DataEnv,
  projectRoot: string,
): DataConfig {
  if (!isAbsolute(projectRoot)) {
    throw new Error('WEB data projectRoot must be absolute');
  }
  const mode = env.WEB_DATA_MODE ?? (env.DEV ? 'mock' : 'production');
  const dataRoot = resolve(projectRoot, env.WEB_DATA_ROOT ?? 'output');
  const fail = (reason: string): never => {
    throw new Error(
      `[web-data] mode=${JSON.stringify(mode)} path=${JSON.stringify(dataRoot)}: ${reason}`,
    );
  };
  if (!['production', 'mock', 'fixture'].includes(mode)) {
    fail('invalid WEB_DATA_MODE');
  }
  if (env.WEB_DATA_ROOT?.trim() === '') {
    fail('WEB_DATA_ROOT must not be empty');
  }
  const maxAgeDays = Number(env.WEB_DATA_MAX_AGE_DAYS ?? '10');
  if (!Number.isFinite(maxAgeDays) || maxAgeDays <= 0) {
    fail('WEB_DATA_MAX_AGE_DAYS must be a finite positive number');
  }
  return { mode: mode as DataMode, dataRoot, maxAgeDays };
}
