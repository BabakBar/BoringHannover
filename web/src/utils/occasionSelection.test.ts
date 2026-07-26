import { describe, expect, test } from 'bun:test';
import type { OccasionSummary } from '../data/types';
import {
  LANDING_OCCASION_LIMIT,
  selectLandingOccasions,
} from './occasionSelection';

function occasion(name: string): OccasionSummary {
  return {
    id: name,
    slug: name,
    name,
    kind: 'festival',
    startDate: '2026-07-01',
    endDate: '2026-07-02',
    location: 'Hannover',
    description: name,
    sourceUrl: 'https://example.com',
    status: 'upcoming',
    programmeCount: 0,
    locationCount: 0,
    programmePath: `occasions/${name}.json`,
    preview: [],
  };
}

describe('selectLandingOccasions', () => {
  test('keeps the landing page to the first two current occasions', () => {
    const occasions = [
      occasion('maschseefest'),
      occasion('fahrmannsfest'),
      occasion('drag-sparks-joy'),
    ];

    expect(LANDING_OCCASION_LIMIT).toBe(2);
    expect(selectLandingOccasions(occasions).map(item => item.name)).toEqual([
      'maschseefest',
      'fahrmannsfest',
    ]);
  });
});
