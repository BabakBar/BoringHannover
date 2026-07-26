import { describe, expect, test } from 'bun:test';
import {
  ALL_RADAR_CATEGORIES,
  getRadarCategoryOptions,
  matchesRadarCategory,
} from './radarCategoryFilter';

describe('getRadarCategoryOptions', () => {
  test('counts categories in the product taxonomy order', () => {
    const options = getRadarCategoryOptions([
      { radarCategory: 'Workshop' },
      { radarCategory: 'Live Music' },
      { radarCategory: 'Workshop' },
      { radarCategory: 'Film' },
    ]);

    expect(options).toEqual([
      { category: 'Live Music', count: 1 },
      { category: 'Workshop', count: 2 },
      { category: 'Film', count: 1 },
    ]);
  });

  test('ignores values outside the public taxonomy', () => {
    expect(getRadarCategoryOptions([
      { radarCategory: 'Unknown' },
      { radarCategory: null },
    ])).toEqual([]);
  });
});

describe('matchesRadarCategory', () => {
  test('all includes every event', () => {
    expect(matchesRadarCategory('Party', ALL_RADAR_CATEGORIES)).toBe(true);
    expect(matchesRadarCategory(null, ALL_RADAR_CATEGORIES)).toBe(true);
  });

  test('a category only includes exact matches', () => {
    expect(matchesRadarCategory('Party', 'Party')).toBe(true);
    expect(matchesRadarCategory('Live Music', 'Party')).toBe(false);
  });
});
