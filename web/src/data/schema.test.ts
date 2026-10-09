import { describe, expect, test } from 'bun:test';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  eventDataSchema,
  occasionProgrammeSchema,
  occasionSummarySchema,
} from './schema';

const outputRoot = fileURLToPath(new URL('../../output/', import.meta.url));
const readJson = (path: string): unknown =>
  JSON.parse(readFileSync(path, 'utf8'));

const legacyOccasion = {
  id: 'hannover-festivals:tiergartenfest-hannover',
  slug: 'tiergartenfest-hannover',
  name: 'Tiergartenfest Hannover',
  kind: 'festival',
  startDate: '2026-10-10',
  endDate: '2026-10-10',
  location: 'Tiergarten',
  description: 'Traditionelles Fest.',
  imageUrl: null,
  sourceUrl:
    'https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/Tiergartenfest-Hannover',
  status: 'upcoming',
  programmeCount: 0,
  locationCount: 0,
  programmePath: 'occasions/tiergartenfest-hannover.json',
  preview: [],
};

describe('committed export snapshots', () => {
  test('the published manifest and every programme still parse', () => {
    const manifest = eventDataSchema.parse(
      readJson(join(outputRoot, 'web_events.json')),
    );
    const files = readdirSync(join(outputRoot, 'occasions')).filter((name) =>
      name.endsWith('.json'),
    );

    expect(files.length).toBeGreaterThan(0);
    for (const name of files) {
      expect(
        occasionProgrammeSchema.safeParse(
          readJson(join(outputRoot, 'occasions', name)),
        ).success,
      ).toBe(true);
    }
    // The snapshot changes with every scrape, so only assert what holds for
    // any published data; legacy shapes are covered by the fixtures below.
    for (const occasion of manifest.occasions) {
      expect(files).toContain(occasion.programmePath.replace('occasions/', ''));
    }
  });
});

describe('additive occasion schedule fields', () => {
  test('legacy summaries without schedule evidence parse', () => {
    expect(occasionSummarySchema.parse(legacyOccasion).scheduleConfidence)
      .toBeUndefined();
  });

  test('every new enum value the backend can publish is accepted', () => {
    for (const scheduleConfidence of ['continuous', 'discrete', 'unknown']) {
      for (const sourceStatus of [
        'scheduled',
        'cancelled',
        'postponed',
        'rescheduled',
      ]) {
        const parsed = occasionSummarySchema.parse({
          ...legacyOccasion,
          scheduleConfidence,
          sourceStatus,
          previousStartDate: '2026-10-03',
          hoursText: '10.10.2026 ab 13:00 bis 18:30 Uhr',
          ...(scheduleConfidence === 'unknown'
            ? {}
            : {
                occurrences: [
                  { date: '2026-10-10', startTime: '13:00', endTime: '18:30' },
                  { date: '2026-10-11' },
                ],
              }),
        });
        expect(parsed.sourceStatus).toBe(sourceStatus as never);
        if (scheduleConfidence !== 'unknown') {
          expect(parsed.occurrences?.[1]).toEqual({ date: '2026-10-11' });
        }
      }
    }
  });

  test('malformed schedule facts are rejected', () => {
    for (const invalid of [
      { sourceStatus: 'abgesagt' },
      { scheduleConfidence: 'weekly' },
      { occurrences: [{ date: '10.10.2026' }] },
      { occurrences: [{ date: '2026-10-10', startTime: '25:00' }] },
      { occurrences: [{ date: '2026-10-10', startTime: '18' }] },
      { previousStartDate: '2026-02-31' },
      // Occurrences are confirmed dates; they need a parsed schedule.
      { occurrences: [{ date: '2026-10-10', startTime: '13:00' }] },
      {
        scheduleConfidence: 'unknown',
        occurrences: [{ date: '2026-10-10', startTime: '13:00' }],
      },
    ]) {
      expect(
        occasionSummarySchema.safeParse({ ...legacyOccasion, ...invalid })
          .success,
      ).toBe(false);
    }
  });
});
