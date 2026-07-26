import type { Concert } from '../data/types';

export const ALL_RADAR_CATEGORIES = 'all';

export const RADAR_CATEGORIES = [
  'Live Music',
  'Party',
  'Culture & Community',
  'Workshop',
  'Sport',
  'Market',
  'Film',
  'Food & Drink',
] as const;

export type RadarCategory = (typeof RADAR_CATEGORIES)[number];
export type RadarCategorySelection =
  | RadarCategory
  | typeof ALL_RADAR_CATEGORIES;

export interface RadarCategoryOption {
  category: RadarCategory;
  count: number;
}

function getRadarCategory(
  category: string | null | undefined,
): RadarCategory | null {
  return RADAR_CATEGORIES.includes(category as RadarCategory)
    ? category as RadarCategory
    : null;
}

export function getRadarCategoryOptions(
  concerts: ReadonlyArray<Pick<Concert, 'radarCategory'>>,
): RadarCategoryOption[] {
  const counts = new Map<RadarCategory, number>(
    RADAR_CATEGORIES.map(category => [category, 0]),
  );

  for (const concert of concerts) {
    const category = getRadarCategory(concert.radarCategory);
    if (!category) continue;
    counts.set(category, (counts.get(category) ?? 0) + 1);
  }

  return RADAR_CATEGORIES.flatMap(category => {
    const count = counts.get(category) ?? 0;
    return count > 0 ? [{ category, count }] : [];
  });
}

export function matchesRadarCategory(
  eventCategory: string | null | undefined,
  selectedCategory: string,
): boolean {
  return (
    selectedCategory === ALL_RADAR_CATEGORIES
    || eventCategory === selectedCategory
  );
}
