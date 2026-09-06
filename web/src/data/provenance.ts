import type { DataMode } from './resolve';
import type { EventData } from './types';

export interface Provenance {
  mode: DataMode;
  source: 'file' | 'mock';
  dataRoot: string;
  revision: string;
  week: number;
  year: number;
  updatedAtISO: string | null;
  movieCount: number;
  concertCount: number;
  occasionCount: number;
  orphanCount: number;
}

export function createProvenance(
  data: EventData,
  input: Pick<
    Provenance,
    'mode' | 'source' | 'dataRoot' | 'revision' | 'orphanCount'
  >,
): Provenance {
  return {
    ...input,
    week: data.meta.week,
    year: data.meta.year,
    updatedAtISO: data.meta.updatedAtISO ?? null,
    movieCount: data.movies.reduce(
      (count, day) => count + day.movies.length,
      0,
    ),
    concertCount: data.concerts.length,
    occasionCount: data.occasions.length,
  };
}

export function publicProvenance({
  dataRoot: _dataRoot,
  ...publicFields
}: Provenance) {
  return publicFields;
}
