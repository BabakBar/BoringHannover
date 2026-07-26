// Data loader for BoringHannover events
// Loads from web_events.json if available, falls back to mock data

import type { EventData, OccasionProgramme } from './types';
import { mockData } from './mock';
import * as fs from 'node:fs';
import * as path from 'node:path';

/**
 * Load event data from web_events.json or fallback to mock data.
 *
 * The JSON file is expected to be at:
 * - ../../output/web_events.json (relative to web/ folder)
 * - Or at the path specified by WEB_EVENTS_PATH env var
 */
const dataDirectories = [
  path.join(process.cwd(), '..', 'output'),
  path.join(process.cwd(), 'output'),
];

function normalizeEventData(data: EventData): EventData {
  return {
    ...data,
    movies: Array.isArray(data.movies) ? data.movies : [],
    concerts: Array.isArray(data.concerts) ? data.concerts : [],
    occasions: Array.isArray(data.occasions) ? data.occasions : [],
  };
}

export function loadEventData(): EventData {
  const possiblePaths = [
    ...dataDirectories.map(directory => path.join(directory, 'web_events.json')),
    process.env.WEB_EVENTS_PATH,
  ].filter(Boolean) as string[];

  for (const jsonPath of possiblePaths) {
    try {
      if (fs.existsSync(jsonPath)) {
        const content = fs.readFileSync(jsonPath, 'utf-8');
        return normalizeEventData(JSON.parse(content) as EventData);
      }
    } catch {
      // Failed to load from this path, try next
    }
  }

  // Fallback to mock data
  return mockData;
}

/**
 * Load a programme referenced by a trusted occasion summary.
 */
export function loadOccasionProgramme(
  programmePath: string,
): OccasionProgramme | null {
  if (!/^occasions\/[a-z0-9-]+\.json$/.test(programmePath)) {
    return null;
  }

  for (const directory of dataDirectories) {
    const jsonPath = path.join(directory, programmePath);
    try {
      if (!fs.existsSync(jsonPath)) continue;
      return JSON.parse(
        fs.readFileSync(jsonPath, 'utf-8'),
      ) as OccasionProgramme;
    } catch {
      // A broken programme must not prevent other occasion pages from building.
    }
  }

  return null;
}

/**
 * Check if we're using mock data or real data
 */
export function isUsingMockData(): boolean {
  const possiblePaths = [
    ...dataDirectories.map(directory => path.join(directory, 'web_events.json')),
  ];

  return !possiblePaths.some(p => fs.existsSync(p));
}
