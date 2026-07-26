import type { Concert } from '../data/types';

export const ALL_GENRES = 'all';

export const CANONICAL_GENRES = [
  'Rock',
  'Punk / Hardcore',
  'Metal',
  'Pop',
  'Hip-Hop',
  'Electronic',
  'Jazz / Blues',
  'Klassik',
  'Folk / World',
] as const;

export type CanonicalGenre = (typeof CANONICAL_GENRES)[number];
export type GenreSelection = CanonicalGenre | typeof ALL_GENRES;

export interface GenreOption {
  genre: CanonicalGenre;
  count: number;
}

export function getCanonicalGenre(
  genre: string | null | undefined,
): CanonicalGenre | null {
  return CANONICAL_GENRES.includes(genre as CanonicalGenre)
    ? genre as CanonicalGenre
    : null;
}

export function getGenreOptions(
  concerts: ReadonlyArray<Pick<Concert, 'genre'>>,
): GenreOption[] {
  const counts = new Map<CanonicalGenre, number>(
    CANONICAL_GENRES.map((genre) => [genre, 0]),
  );

  for (const concert of concerts) {
    const genre = getCanonicalGenre(concert.genre);
    if (!genre) continue;
    counts.set(genre, (counts.get(genre) ?? 0) + 1);
  }

  return CANONICAL_GENRES.flatMap((genre) => {
    const count = counts.get(genre) ?? 0;
    return count > 0 ? [{ genre, count }] : [];
  });
}

export function matchesGenre(
  eventGenre: string | null | undefined,
  selectedGenre: string,
): boolean {
  return selectedGenre === ALL_GENRES || eventGenre === selectedGenre;
}
