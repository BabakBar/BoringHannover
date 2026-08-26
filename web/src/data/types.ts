// Type definitions for BoringHannover event data

export interface Movie {
  title: string;
  year?: number | null;
  time: string;
  /** Canonical cinema name. Absent only in exports created before 2026-08. */
  venue?: string | null;
  duration?: string | null;
  language?: string | null;
  subtitles?: string | null;
  rating?: string | null;
  genre?: string | null;
  url?: string | null;
}

export interface MovieDay {
  day: string;    // "FRI", "SAT", etc.
  date: string;   // "21.11"
  movies: Movie[];
}

export interface Concert {
  title: string;
  date: string;   // "29 Nov" or "28 Mar 2026"
  dateISO?: string | null; // "2026-07-29"
  day: string;    // "Sa", "Fr", etc.
  time?: string | null;
  timeConfidence?: "confirmed" | "fallback" | null;
  endTime?: string | null;
  venue: string;
  url?: string | null;
  eventType?: string | null;    // "concert", "sport", "show"
  radarCategory?: string | null;
  genre?: string | null;        // "Konzert", "Festival", etc.
  programmeCategory?: string | null;
  description?: string | null;  // Short description/subtitle
  imageUrl?: string | null;
  sourceName?: string | null;
  status?: string | null;       // "available", "sold_out"
}

export type OccasionStatus = 'upcoming' | 'happening_now' | 'final_weekend';

export interface OccasionSummary {
  id: string;
  slug: string;
  name: string;
  kind: string;
  startDate: string;
  endDate: string;
  location: string;
  description: string;
  imageUrl?: string | null;
  sourceUrl: string;
  status: OccasionStatus;
  programmeCount: number;
  locationCount: number;
  programmePath: string;
  preview: Concert[];
}

export interface OccasionProgramme {
  meta: {
    updatedAt: string;
  };
  occasion: OccasionSummary;
  programme: Concert[];
}

export interface EventMeta {
  week: number;
  year: number;
  /** Display string, e.g. "Tue 28 Jul 11:01". Not parseable. */
  updatedAt: string;
  /** ISO-8601 twin of updatedAt. Absent in data written before it existed. */
  updatedAtISO?: string;
}

export interface EventData {
  meta: EventMeta;
  movies: MovieDay[];
  concerts: Concert[];
  occasions: OccasionSummary[];
}
