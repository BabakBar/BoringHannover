import type { z } from 'zod';
import type {
  concertSchema,
  occasionOccurrenceSchema,
  sourceStatusSchema,
  occasionPlaceSchema,
  occasionSummarySchema,
  occasionProgrammeSchema,
  eventDataSchema,
} from './schema';

export type Concert = z.infer<typeof concertSchema>;
export type OccasionOccurrence = z.infer<typeof occasionOccurrenceSchema>;
export type SourceStatus = z.infer<typeof sourceStatusSchema>;
export type OccasionPlace = z.infer<typeof occasionPlaceSchema>;
export type OccasionSummary = z.infer<typeof occasionSummarySchema>;
export type OccasionProgramme = z.infer<typeof occasionProgrammeSchema>;
export type EventData = z.infer<typeof eventDataSchema>;
