import { expect, test } from 'bun:test';
import {
  ALL_RADAR_CATEGORIES,
  getRadarCategoryOptions,
  matchesRadarCategory,
} from './radarCategoryFilter';

test('category options follow the product taxonomy and ignore unknowns', () => {
  expect(
    getRadarCategoryOptions([
      { radarCategory: 'Workshop' },
      { radarCategory: 'Live Music' },
      { radarCategory: 'Workshop' },
      { radarCategory: 'Film' },
      { radarCategory: 'Unknown' },
      { radarCategory: null },
    ]),
  ).toEqual([
    { category: 'Live Music', count: 1 },
    { category: 'Workshop', count: 2 },
    { category: 'Film', count: 1 },
  ]);
});

test('"all" matches everything; a category matches only itself', () => {
  expect(matchesRadarCategory('Party', ALL_RADAR_CATEGORIES)).toBe(true);
  expect(matchesRadarCategory(null, ALL_RADAR_CATEGORIES)).toBe(true);
  expect(matchesRadarCategory('Party', 'Party')).toBe(true);
  expect(matchesRadarCategory('Live Music', 'Party')).toBe(false);
});
