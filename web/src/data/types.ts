import type { z } from 'zod';
import type {
  movieSchema,
  movieDaySchema,
  concertSchema,
  occasionStatusSchema,
  occasionOccurrenceSchema,
  scheduleConfidenceSchema,
  sourceStatusSchema,
  occasionPlaceSchema,
  occasionAdmissionSchema,
  occasionSummarySchema,
  occasionProgrammeSchema,
  eventMetaSchema,
  eventDataSchema,
} from './schema';

export type Movie = z.infer<typeof movieSchema>;
export type MovieDay = z.infer<typeof movieDaySchema>;
export type Concert = z.infer<typeof concertSchema>;
export type OccasionStatus = z.infer<typeof occasionStatusSchema>;
export type OccasionOccurrence = z.infer<typeof occasionOccurrenceSchema>;
export type ScheduleConfidence = z.infer<typeof scheduleConfidenceSchema>;
export type SourceStatus = z.infer<typeof sourceStatusSchema>;
export type OccasionPlace = z.infer<typeof occasionPlaceSchema>;
export type OccasionAdmission = z.infer<typeof occasionAdmissionSchema>;
export type OccasionSummary = z.infer<typeof occasionSummarySchema>;
export type OccasionProgramme = z.infer<typeof occasionProgrammeSchema>;
export type EventMeta = z.infer<typeof eventMetaSchema>;
export type EventData = z.infer<typeof eventDataSchema>;
