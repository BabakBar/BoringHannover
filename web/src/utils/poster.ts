import { createHash } from 'node:crypto';
import type { OccasionSummary } from '../data/types';
import { appointmentHours } from './occasionSheet';
import { addDays } from './occasionStatus';
import { occasionPictogram, pictogramDots } from './pictogram';

// Share poster (#114 §6): 1200 × 630, owned type and pictogram only. Link
// previews cache it for weeks, so it says absolute dates only, and its URL
// carries a hash of the drawing so a changed fact gets a new image.

const INK = '#141312';
const AMBER = '#f0b445';
const RED = '#ff5a4d';
const PAPER = '#f3f1ec';
const DIM = '#a8a49c';
/** Space Mono's advance width per em. */
const ADVANCE = 0.612;
const COLUMN = 680;

function escape(text: string) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

const dayMonth = (date: string) => `${date.slice(8, 10)}.${date.slice(5, 7)}`;

const weekday = (date: string) => new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', weekday: 'short' })
  .format(new Date(`${date}T00:00:00Z`)).toUpperCase();

/** The facts line's schedule; null when no short wording is true for the whole run. */
function scheduleText(occasion: OccasionSummary): string | null {
  const { startDate, endDate, scheduleConfidence } = occasion;
  const confirmed = scheduleConfidence === 'continuous' || scheduleConfidence === 'discrete'
    ? occasion.occurrences ?? [] : [];
  if (startDate === endDate) {
    const occurrence = confirmed.find(item => item.date === startDate);
    const hours = occurrence && appointmentHours(occurrence);
    return hours ? `${weekday(startDate)} ${hours.toUpperCase()}` : weekday(startDate);
  }
  if (scheduleConfidence === 'discrete') return 'SELECTED DATES';
  const hours = new Set(confirmed.map(appointmentHours));
  const everyDay = new Set(confirmed.map(item => item.date)).size === confirmed.length &&
    addDays(startDate, confirmed.length - 1) === endDate;
  if (scheduleConfidence === 'continuous' && everyDay && hours.size === 1 && !hours.has(null)) {
    return `DAILY ${[...hours][0]!.toUpperCase()}`;
  }
  // "MON–TUE" for a four-week run would read as two days.
  return addDays(startDate, 6) >= endDate ? `${weekday(startDate)}–${weekday(endDate)}` : null;
}

export function posterFacts(occasion: OccasionSummary) {
  const { startDate, endDate, sourceStatus } = occasion;
  const status = sourceStatus === 'cancelled' ? 'CANCELLED · '
    : sourceStatus === 'postponed' ? 'POSTPONED · '
      : '';
  const place = occasion.area === 'region' && occasion.place?.municipality
    ? `DAY TRIP · ${occasion.place.municipality.toUpperCase()}`
    : 'CITY OCCASION · HANNOVER';
  const venue = (occasion.place?.venue ?? occasion.location).toUpperCase();
  const schedule = scheduleText(occasion);
  return {
    kicker: `${status}${place}`,
    date: startDate === endDate ? dayMonth(startDate) : `${dayMonth(startDate)}–${dayMonth(endDate)}`,
    year: startDate.slice(0, 4) === endDate.slice(0, 4)
      ? startDate.slice(0, 4)
      : `${startDate.slice(0, 4)}–${endDate.slice(0, 4)}`,
    info: schedule ? `${schedule} · ${venue}` : venue,
  };
}

function wrap(text: string, perLine: number): string[] {
  const lines: string[] = [];
  let line = '';
  for (const word of text.split(/\s+/)) {
    let rest = word;
    while (rest.length > perLine) {
      if (line) { lines.push(line); line = ''; }
      lines.push(`${rest.slice(0, perLine - 1)}-`);
      rest = rest.slice(perLine - 1);
    }
    const candidate = line ? `${line} ${rest}` : rest;
    if (candidate.length > perLine) { lines.push(line); line = rest; } else line = candidate;
  }
  if (line) lines.push(line);
  return lines;
}

export function posterSvg(occasion: OccasionSummary): string {
  const { kicker, date, year, info } = posterFacts(occasion);
  const left = 72;
  const perLine = (size: number) => Math.floor(COLUMN / (size * ADVANCE));
  // Date (letter-spacing -4) and year end before the pictogram at x = 810.
  const yearWidth = year.length * 22 * ADVANCE;
  const dateSize = Math.min(150, Math.floor(((800 - left - 14 - yearWidth) / date.length + 4) / ADVANCE));
  const dateWidth = date.length * (dateSize * ADVANCE - 4);
  const name = occasion.name.toUpperCase();
  let nameSize = 64;
  let lines = wrap(name, perLine(nameSize));
  for (const size of [58, 52, 46, 40, 34]) {
    if (lines.length <= 3) break;
    nameSize = size;
    lines = wrap(name, perLine(size));
  }
  if (lines.length > 3) {
    lines = [...lines.slice(0, 2), `${lines.slice(2).join(' ').slice(0, perLine(nameSize) - 1)}…`];
  }
  const dateBaseline = 150 + dateSize * 0.78;
  const nameTop = dateBaseline + 28;
  const nameLines = lines.map((line, i) =>
    `<text x="${left}" y="${nameTop + nameSize * (i + 0.9)}" font-size="${nameSize}" font-weight="700" fill="${PAPER}" letter-spacing="-1">${escape(line)}</text>`,
  ).join('');
  const infoSize = Math.min(24, Math.floor(1056 / (info.length * ADVANCE)));
  // 4 px letter spacing; stops before the site name on the right.
  const kickerSize = Math.min(22, Math.floor((700 / kicker.length - 4) / ADVANCE));
  const icon = pictogramDots(occasionPictogram(occasion), 30, { fill: AMBER, x: 810, y: 96 });
  // The ■ glyph is missing from the font subset: the kicker squares are rects.
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" font-family="Space Mono">
<defs><pattern id="led" width="6" height="6" patternUnits="userSpaceOnUse"><circle cx="3" cy="3" r="1" fill="${AMBER}" opacity="0.05"/></pattern></defs>
<rect width="1200" height="630" fill="${INK}"/><rect width="1200" height="630" fill="url(#led)"/>
<rect x="${left}" y="78" width="11" height="11" fill="${RED}"/><rect x="${left + 18}" y="78" width="11" height="11" fill="${RED}"/><rect x="${left + 36}" y="78" width="11" height="11" fill="${RED}"/>
<text x="${left + 64}" y="89" font-size="${kickerSize}" fill="${RED}" letter-spacing="4">${escape(kicker)}</text>
<text x="${left - 4}" y="${dateBaseline}" font-size="${dateSize}" font-weight="700" fill="${AMBER}" letter-spacing="-4">${escape(date)}</text>
<text x="${left - 4 + dateWidth + 14}" y="${dateBaseline}" font-size="22" fill="${DIM}">${year}</text>
${nameLines}
${icon}
<line x1="${left}" y1="532" x2="1128" y2="532" stroke="${AMBER}" stroke-opacity="0.25" stroke-dasharray="2 6"/>
<text x="${left}" y="574" font-size="${infoSize}" fill="${DIM}">${escape(info)}</text>
<text x="1128" y="89" font-size="20" fill="${DIM}" text-anchor="end" letter-spacing="2">BORINGHANNOVER.DE</text>
</svg>`;
}

/** The poster's path: a changed drawing gets a new URL, so previews refresh. */
export function posterPath(occasion: OccasionSummary): string {
  const hash = createHash('sha256').update(posterSvg(occasion)).digest('hex').slice(0, 8);
  return `/occasion-posters/${occasion.slug}-${hash}.png`;
}
