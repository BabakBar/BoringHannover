// Data loader for KinoWeek events
// Loads from web_events.json if available, falls back to mock data

import type { EventData } from './types';
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
export function loadEventData(): EventData {
  // Try to load from JSON file
  const possiblePaths = [
    // Relative to project root
    path.join(process.cwd(), '..', 'output', 'web_events.json'),
    path.join(process.cwd(), 'output', 'web_events.json'),
    // Absolute path from env
    process.env.WEB_EVENTS_PATH,
  ].filter(Boolean) as string[];

  for (const jsonPath of possiblePaths) {
    try {
      if (fs.existsSync(jsonPath)) {
        const content = fs.readFileSync(jsonPath, 'utf-8');
        const data = JSON.parse(content) as EventData;
        return data;
      }
    } catch {
      // Failed to load from this path, try next
    }
  }

  // Fallback to mock data
  return mockData;
}

/**
 * Check if we're using mock data or real data
 */
export function isUsingMockData(): boolean {
  const possiblePaths = [
    path.join(process.cwd(), '..', 'output', 'web_events.json'),
    path.join(process.cwd(), 'output', 'web_events.json'),
  ];

  return !possiblePaths.some(p => fs.existsSync(p));
}
