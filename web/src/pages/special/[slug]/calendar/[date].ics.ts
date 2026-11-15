import type { APIRoute } from 'astro';
import { loadEventData, loadOccasionProgramme } from '../../../../data/loader';
import type { OccasionSummary } from '../../../../data/types';
import { calendarAppointments, occasionCalendar, type CalendarAppointment } from '../../../../utils/occasionCalendar';

export const prerender = true;

export function getStaticPaths() {
  const data = loadEventData();
  const now = new Date();
  return data.occasions.flatMap(summary => {
    const occasion = loadOccasionProgramme(summary.programmePath)!.occasion;
    return calendarAppointments(occasion, now).map(appointment => ({
      params: { slug: occasion.slug, date: appointment.occurrence.date },
      props: { occasion, appointment, updatedAt: data.meta.updatedAtISO ?? now.toISOString() },
    }));
  });
}

export const GET: APIRoute = ({ props }) => {
  const { occasion, appointment, updatedAt } = props as {
    occasion: OccasionSummary; appointment: CalendarAppointment; updatedAt: string;
  };
  return new Response(occasionCalendar(occasion, appointment, updatedAt), {
    headers: { 'Content-Type': 'text/calendar; charset=utf-8' },
  });
};
