import { z } from 'zod';

// Unknown object keys are intentionally accepted and stripped by z.object().
// #29 validates the fields consumed by this UI; #30 owns the versioned contract
// and whether additive exporter fields should be retained or rejected.
const optionalText = z.string().nullish();
const count = z.number().int().nonnegative();
export const movieSchema = z.object({
  title: z.string(),
  year: z.number().int().nullish(),
  time: z.string(),
  venue: optionalText.describe(
    'Canonical cinema name. Absent only in exports created before 2026-08.',
  ),
  duration: optionalText,
  language: optionalText,
  subtitles: optionalText,
  rating: optionalText,
  genre: optionalText,
  url: optionalText,
});
export const movieDaySchema = z.object({
  day: z.string(),
  date: z.string(),
  movies: z.array(movieSchema),
});
export const concertSchema = z.object({
  title: z.string(),
  date: z.string(),
  dateISO: z.iso.date().nullish(),
  day: z.string(),
  time: optionalText,
  timeConfidence: z.enum(['confirmed', 'fallback']).nullish(),
  endTime: optionalText,
  venue: z.string(),
  url: optionalText,
  eventType: optionalText,
  radarCategory: optionalText,
  genre: optionalText,
  programmeCategory: optionalText,
  description: optionalText,
  imageUrl: optionalText,
  sourceName: optionalText,
  status: optionalText,
});
export const occasionStatusSchema = z.enum([
  'upcoming',
  'happening_now',
  'final_weekend',
]);
export const occasionSummarySchema = z.object({
  id: z.string().min(1),
  slug: z.string().regex(/^[a-z0-9-]+$/),
  name: z.string(),
  kind: z.string(),
  startDate: z.iso.date(),
  endDate: z.iso.date(),
  location: z.string(),
  description: z.string(),
  imageUrl: optionalText,
  sourceUrl: z.string(),
  status: occasionStatusSchema,
  programmeCount: count,
  locationCount: count,
  programmePath: z.string().regex(/^occasions\/[a-z0-9-]+\.json$/),
  preview: z.array(concertSchema),
});
export const occasionProgrammeSchema = z.object({
  meta: z.object({ updatedAt: z.string() }),
  occasion: occasionSummarySchema,
  programme: z.array(concertSchema),
});
export const eventMetaSchema = z.object({
  week: z.number().int().min(1).max(53),
  year: z.number().int().min(1),
  updatedAt: z
    .string()
    .describe(
      'Display string, e.g. Tue 28 Jul 11:01. Not parseable; use updatedAtISO.',
    ),
  // Legacy mock data has no machine timestamp; the loader requires it for production.
  updatedAtISO: z.iso.datetime({ offset: true }).optional(),
});
export const eventDataSchema = z.object({
  meta: eventMetaSchema,
  movies: z.array(movieDaySchema),
  concerts: z.array(concertSchema),
  occasions: z.array(occasionSummarySchema),
});
