import { describe, expect, test } from 'bun:test';
import {
  ALL_GENRES,
  getCanonicalGenre,
  getGenreOptions,
  matchesGenre,
} from './genreFilter';

describe('getGenreOptions', () => {
  test('counts canonical genres in taxonomy order', () => {
    const options = getGenreOptions([
      { genre: 'Electronic' },
      { genre: 'Punk / Hardcore' },
      { genre: 'Electronic' },
      { genre: null },
      {},
    ]);

    expect(options).toEqual([
      { genre: 'Punk / Hardcore', count: 1 },
      { genre: 'Electronic', count: 2 },
    ]);
  });

  test('ignores noncanonical source labels', () => {
    const options = getGenreOptions([
      { genre: 'Garage Punk' },
      { genre: 'Mit Big Honey' },
      { genre: 'Electronic' },
    ]);

    expect(options).toEqual([{ genre: 'Electronic', count: 1 }]);
  });
});

describe('getCanonicalGenre', () => {
  test('keeps canonical values and rejects arbitrary labels', () => {
    expect(getCanonicalGenre('Electronic')).toBe('Electronic');
    expect(getCanonicalGenre('Garage Punk')).toBeNull();
    expect(getCanonicalGenre(null)).toBeNull();
  });
});

describe('matchesGenre', () => {
  test('all includes classified and unclassified events', () => {
    expect(matchesGenre('Electronic', ALL_GENRES)).toBe(true);
    expect(matchesGenre(null, ALL_GENRES)).toBe(true);
    expect(matchesGenre(undefined, ALL_GENRES)).toBe(true);
  });

  test('a selected genre only includes exact canonical matches', () => {
    expect(matchesGenre('Electronic', 'Electronic')).toBe(true);
    expect(matchesGenre('Rock', 'Electronic')).toBe(false);
    expect(matchesGenre(null, 'Electronic')).toBe(false);
  });
});
