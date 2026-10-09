import { expect, test } from 'bun:test';
import {
  ALL_GENRES,
  getCanonicalGenre,
  getGenreOptions,
  matchesGenre,
} from './genreFilter';

test('genre options count canonical genres in taxonomy order', () => {
  expect(
    getGenreOptions([
      { genre: 'Electronic' },
      { genre: 'Punk / Hardcore' },
      { genre: 'Electronic' },
      { genre: 'Garage Punk' },
      { genre: 'Mit Big Honey' },
      { genre: null },
      {},
    ]),
  ).toEqual([
    { genre: 'Punk / Hardcore', count: 1 },
    { genre: 'Electronic', count: 2 },
  ]);
  expect(getCanonicalGenre('Electronic')).toBe('Electronic');
  expect(getCanonicalGenre('Garage Punk')).toBeNull();
  expect(getCanonicalGenre(null)).toBeNull();
});

test('"all" matches everything; a genre matches only itself', () => {
  expect(matchesGenre('Electronic', ALL_GENRES)).toBe(true);
  expect(matchesGenre(null, ALL_GENRES)).toBe(true);
  expect(matchesGenre(undefined, ALL_GENRES)).toBe(true);
  expect(matchesGenre('Electronic', 'Electronic')).toBe(true);
  expect(matchesGenre('Rock', 'Electronic')).toBe(false);
  expect(matchesGenre(null, 'Electronic')).toBe(false);
});
