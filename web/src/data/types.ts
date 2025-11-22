// Type definitions for KinoWeek event data

export interface Movie {
  title: string;
  year?: number | null;
  time: string;
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
  day: string;    // "Sa", "Fr", etc.
  time?: string | null;
  venue: string;
  url?: string | null;
  eventType?: string | null;    // "concert", "sport", "show"
  genre?: string | null;        // "Konzert", "Festival", etc.
  description?: string | null;  // Short description/subtitle
  status?: string | null;       // "available", "sold_out"
}

export interface EventMeta {
  week: number;
  year: number;
  updatedAt: string;
}

export interface EventData {
  meta: EventMeta;
  movies: MovieDay[];
  concerts: Concert[];
}
