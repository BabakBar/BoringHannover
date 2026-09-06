import type { z } from 'zod';
import type {
  movieSchema,
  movieDaySchema,
  concertSchema,
  occasionStatusSchema,
  occasionSummarySchema,
  occasionProgrammeSchema,
  eventMetaSchema,
  eventDataSchema,
} from './schema';

export type Movie = z.infer<typeof movieSchema>;
export type MovieDay = z.infer<typeof movieDaySchema>;
export type Concert = z.infer<typeof concertSchema>;
export type OccasionStatus = z.infer<typeof occasionStatusSchema>;
export type OccasionSummary = z.infer<typeof occasionSummarySchema>;
export type OccasionProgramme = z.infer<typeof occasionProgrammeSchema>;
export type EventMeta = z.infer<typeof eventMetaSchema>;
export type EventData = z.infer<typeof eventDataSchema>;
