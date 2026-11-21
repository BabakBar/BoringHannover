import type { OccasionSummary } from '../data/types';
import { appointmentHours } from './occasionSheet';
import { occasionPictogram, pictogramSvg } from './pictogram';
import { addDays } from './occasionStatus';

// Share poster (concept E): 1200×630, owned typography and pictogram only,
// absolute dates only because platforms cache previews for weeks.

const INK = '#141312';
const AMBER = '#f0b445';
const RED = '#ff5a4d';
const PAPER = '#f3f1ec';
const DIM = '#a8a49c';
const ADVANCE = 0.612; // Space Mono advance width per em.

function escape(text: string) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function dm(iso: string) {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

function weekday(iso: string) {
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', weekday: 'short' })
    .format(new Date(`${iso}T00:00:00Z`)).toUpperCase();
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

export function posterFacts(occasion: OccasionSummary) {
  const { startDate, endDate } = occasion;
  const occurrences = occasion.scheduleConfidence === 'continuous' || occasion.scheduleConfidence === 'discrete'
    ? occasion.occurrences ?? [] : [];
  const hours = new Set(occurrences.map(appointmentHours));
  const date = startDate === endDate ? dm(startDate) : `${dm(startDate)}–${dm(endDate)}`;
  const year = startDate.slice(0, 4) === endDate.slice(0, 4) ? startDate.slice(0, 4) : `${startDate.slice(0, 4)}–${endDate.slice(0, 4)}`;
  let when: string;
  if (startDate === endDate) {
    const time = occurrences[0] ? appointmentHours(occurrences[0]) : null;
    when = time ? `${weekday(startDate)} ${time}` : weekday(startDate);
  } else if (occasion.scheduleConfidence === 'discrete') {
    when = 'SELECTED DATES';
  } else if (
    occasion.scheduleConfidence === 'continuous' && hours.size === 1 && !hours.has(null) &&
    addDays(startDate, occurrences.length - 1) === endDate
  ) {
    when = `DAILY ${[...hours][0]}`;
  } else {
    when = `${weekday(startDate)}–${weekday(endDate)}`;
  }
  const venue = occasion.place?.venue ?? occasion.location;
  const kicker = occasion.area === 'region' && occasion.place?.municipality
    ? `DAY TRIP · ${occasion.place.municipality.toUpperCase()}`
    : 'CITY OCCASION · HANNOVER';
  return { date, year, when, venue, kicker };
}

export function posterSvg(occasion: OccasionSummary): string {
  const { date, year, when, venue, kicker } = posterFacts(occasion);
  const left = 72;
  const columnWidth = 680;
  const dateSize = Math.min(150, Math.floor(columnWidth / (date.length * ADVANCE)));
  const name = occasion.name.toUpperCase();
  let nameSize = 64;
  let lines = wrap(name, Math.floor(columnWidth / (nameSize * ADVANCE)));
  for (const size of [58, 52, 46, 40, 34]) {
    if (lines.length <= 3) break;
    nameSize = size;
    lines = wrap(name, Math.floor(columnWidth / (size * ADVANCE)));
  }
  if (lines.length > 3) lines = [...lines.slice(0, 2), `${lines.slice(2).join(' ').slice(0, Math.floor(columnWidth / (nameSize * ADVANCE)) - 1)}…`];
  const dateBaseline = 150 + dateSize * 0.78;
  const nameTop = dateBaseline + 28;
  const nameLines = lines.map((line, i) =>
    `<text x="${left}" y="${nameTop + nameSize * (i + 0.9)}" font-size="${nameSize}" font-weight="700" fill="${PAPER}" letter-spacing="-1">${escape(line)}</text>`,
  ).join('');
  const info = `${when} · ${venue.toUpperCase()}`;
  const infoSize = Math.min(24, Math.floor(1056 / (info.length * ADVANCE)));
  const icon = pictogramSvg(occasionPictogram(occasion), 30, { lit: AMBER, x: 810, y: 96, standalone: false });
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" font-family="Space Mono">
<defs><pattern id="led" width="6" height="6" patternUnits="userSpaceOnUse"><circle cx="3" cy="3" r="1" fill="${AMBER}" opacity="0.05"/></pattern></defs>
<rect width="1200" height="630" fill="${INK}"/><rect width="1200" height="630" fill="url(#led)"/>
<rect x="${left}" y="78" width="11" height="11" fill="${RED}"/><rect x="${left + 18}" y="78" width="11" height="11" fill="${RED}"/><rect x="${left + 36}" y="78" width="11" height="11" fill="${RED}"/>
<text x="${left + 64}" y="89" font-size="22" fill="${RED}" letter-spacing="4">${escape(kicker)}</text>
<text x="${left - 4}" y="${dateBaseline}" font-size="${dateSize}" font-weight="700" fill="${AMBER}" letter-spacing="-4">${escape(date)}</text>
<text x="${left + date.length * dateSize * ADVANCE + 6}" y="${dateBaseline}" font-size="22" fill="${DIM}">${year}</text>
${nameLines}
${icon}
<line x1="${left}" y1="532" x2="1128" y2="532" stroke="${AMBER}" stroke-opacity="0.25" stroke-dasharray="2 6"/>
<text x="${left}" y="574" font-size="${infoSize}" fill="${DIM}">${escape(info)}</text>
<text x="1128" y="89" font-size="20" fill="${DIM}" text-anchor="end" letter-spacing="2">BORINGHANNOVER.DE</text>
</svg>`;
}
