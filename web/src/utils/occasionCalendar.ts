import type { OccasionOccurrence, OccasionSummary } from '../data/types';
import { occasionSourceLink } from './occasionSource';
import { placeAddress } from './occasionSheet';
import { addDays, berlinClock, OCCASION_HORIZON_DAYS, type OccasionSchedule } from './occasionStatus';

export interface CalendarAppointment {
  occurrence: OccasionOccurrence;
  startsAt: number | null;
  endsAt: number | null;
  expiresAt: number;
}

/** Resolve modern Berlin wall time only when it names one unambiguous instant. */
function berlinInstant(date: string, time: string): number | null {
  if (time === '24:00') return berlinInstant(addDays(date, 1), '00:00');
  const [hour, minute] = time.split(':').map(Number);
  const wall = Date.parse(`${date}T${time}:00Z`);
  const candidates = [60, 120].map(offset => wall - offset * 60000).filter(value => {
    const clock = berlinClock(new Date(value));
    return clock.date === date && clock.minutes === hour * 60 + minute;
  });
  // The spring gap and repeated autumn hour need evidence the source does not supply.
  return candidates.length === 1 ? candidates[0] : null;
}

/** Only explicit appointments, or a single sourced date; never expand a season. */
export function calendarAppointments(schedule: OccasionSchedule, now: Date): CalendarAppointment[] {
  if (schedule.sourceStatus === 'cancelled' || schedule.sourceStatus === 'postponed') return [];
  const today = berlinClock(now).date;
  const horizon = addDays(today, OCCASION_HORIZON_DAYS);
  const parsed = schedule.scheduleConfidence === 'continuous' || schedule.scheduleConfidence === 'discrete';
  const occurrences = parsed && schedule.occurrences?.length
    ? schedule.occurrences
    : schedule.scheduleConfidence !== 'discrete' && schedule.startDate === schedule.endDate
      ? [{ date: schedule.startDate }] : [];
  const result: CalendarAppointment[] = [];
  for (const occurrence of occurrences) {
    const { date, startTime, endTime } = occurrence;
    if (date < today || date > horizon || date < schedule.startDate || date > schedule.endDate ||
        occurrences.filter(item => item.date === date).length !== 1) continue;
    const startsAt = startTime ? berlinInstant(date, startTime) : null;
    const endsAt = endTime ? berlinInstant(date, endTime) : null;
    if ((startTime && startsAt === null) || (endTime && (
      startsAt === null || endsAt === null || endsAt <= startsAt
    ))) continue;
    const expiresAt = endsAt ?? berlinInstant(addDays(date, 1), '00:00');
    if (expiresAt !== null && now.getTime() < expiresAt) result.push({ occurrence, startsAt, endsAt, expiresAt });
  }
  return result.sort((left, right) => left.occurrence.date.localeCompare(right.occurrence.date));
}

function textValue(value: string): string {
  return value.replaceAll('\\', '\\\\').replace(/\r\n|\r|\n/g, '\\n').replaceAll(';', '\\;').replaceAll(',', '\\,');
}

function foldLine(line: string): string {
  const encoder = new TextEncoder();
  let result = '';
  let octets = 0;
  for (const character of line) {
    const size = encoder.encode(character).length;
    if (octets + size > 75) {
      result += '\r\n ';
      octets = 1;
    }
    result += character;
    octets += size;
  }
  return result;
}

function utcTime(value: number): string {
  return new Date(value).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
}

/** RFC 5545: one VEVENT, UTC instants or an explicitly labelled date reminder. */
export function occasionCalendar(occasion: OccasionSummary, appointment: CalendarAppointment, updatedAt: string): string {
  const { occurrence, startsAt, endsAt } = appointment;
  const reminder = startsAt === null;
  const source = occasionSourceLink(occasion.sourceUrl);
  const notes = [
    occasion.description,
    reminder ? 'Date reminder only. Opening hours are not confirmed.'
      : endsAt === null ? 'No end time is listed.' : '',
    'Check the source for changes. This download does not update automatically.',
  ].filter(Boolean).join('\n\n');
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//boringhannover//City Occasions//EN',
    'CALSCALE:GREGORIAN', 'BEGIN:VEVENT',
    `UID:${encodeURIComponent(occasion.id)}-${occurrence.date}@boringhannover.de`,
    `DTSTAMP:${utcTime(Date.parse(updatedAt))}`,
    `SUMMARY:${textValue(occasion.name + (reminder ? ' (date reminder)' : ''))}`,
    `DESCRIPTION:${textValue(notes)}`,
    `LOCATION:${textValue(occasion.place
      ? `${occasion.place.venue ?? occasion.location}, ${placeAddress(occasion.place)}`
      : occasion.location)}`,
  ];
  if (reminder) {
    lines.push(`DTSTART;VALUE=DATE:${occurrence.date.replaceAll('-', '')}`,
      `DTEND;VALUE=DATE:${addDays(occurrence.date, 1).replaceAll('-', '')}`, 'TRANSP:TRANSPARENT');
  } else {
    lines.push(`DTSTART:${utcTime(startsAt)}`);
    if (endsAt !== null) lines.push(`DTEND:${utcTime(endsAt)}`);
  }
  if (source) lines.push(`URL:${new URL(source.url).href}`);
  lines.push('END:VEVENT', 'END:VCALENDAR');
  return lines.map(foldLine).join('\r\n') + '\r\n';
}
