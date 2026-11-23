import type { OccasionSummary } from '../data/types';

// 11 × 12 LED pictograms. X = lit dot; unlit dots stay faintly visible, like a
// real dot-matrix display.
const PICTOGRAMS = {
  stand: ['XXXXXXXXXXX', 'X.X.X.X.X.X', 'XXXXXXXXXXX', '.X.X.X.X.X.', '.X.......X.', '.X.......X.', '.XXXXXXXXX.', '.X.X.X.X.X.', '.XXXXXXXXX.', '.X.......X.', '.X.......X.', '...........'],
  baum: ['.....X.....', '....XXX....', '...XXXXX...', '..XX.X.XX..', '.XXXXXXXXX.', '..XX.X.XX..', '.XXXXXXXXX.', 'XXXX.X.XXXX', '.....X.....', '.....X.....', '...XXXXX...', '...........'],
  pyramide: ['.XXXXXXXXX.', '.....X.....', '.....X.....', '...XXXXX...', '...X.X.X...', '..XXXXXXX..', '..X.X.X.X..', '.XXXXXXXXX.', '.X.X.X.X.X.', 'XXXXXXXXXXX', 'X.........X', 'XXXXXXXXXXX'],
  laterne: ['.....X.....', '.....X.....', '...XXXXX...', '..X.....X..', '.X..X.X..X.', '.X...X...X.', '.X..X.X..X.', '..X.....X..', '...XXXXX...', '.....X.....', '...........', '...........'],
  kerze: ['.....X.....', '....XXX....', '....XXX....', '.....X.....', '....XXX....', '....X.X....', '....X.X....', '....X.X....', '....X.X....', '....X.X....', '..XXXXXXX..', '.X.......X.'],
  stern: ['.....X.....', '.....X.....', '....XXX....', 'XXXXXXXXXXX', '.XXXXXXXXX.', '..XXXXXXX..', '...XXXXX...', '..XXXXXXX..', '..XXX.XXX..', '.XX.....XX.', '.X.......X.', '...........'],
  note: ['...XXXXXXX.', '...XXXXXXX.', '...X.....X.', '...X.....X.', '...X.....X.', '...X.....X.', '...X.....X.', '.XXX...XXX.', 'XXXX..XXXX.', 'XXXX..XXXX.', '.XX....XX..', '...........'],
  rad: ['...XXXXX...', '..X..X..X..', '.X.X.X.X.X.', 'X...XXX...X', 'XXXXX.XXXXX', 'X...XXX...X', '.X.X.X.X.X.', '..X..X..X..', '...XXXXX...', '....X.X....', '...X...X...', 'XXXXXXXXXXX'],
  kuerbis: ['.....XX....', '......X....', '..XXX.XXX..', '.X..X.X..X.', 'X..X...X..X', 'X..X...X..X', 'X..X...X..X', 'X..X...X..X', '.X..X.X..X.', '..XXX.XXX..', '...........', '...........'],
  feuer: ['.....X.....', '.X...X...X.', '..X..X..X..', '...X...X...', '...........', 'XXX..X..XXX', '...........', '...X...X...', '..X..X..X..', '.X...X...X.', '.....X.....', '...........'],
  fontaene: ['.....X.....', '...X.X.X...', '..X..X..X..', '.X...X...X.', '.X...X...X.', '.....X.....', '...XXXXX...', 'X.........X', 'XXXXXXXXXXX', '.X.......X.', '...........', '...........'],
  tasse: ['...X.X.X...', '..X.X.X....', '...X.X.X...', '...........', 'XXXXXXXX...', 'X......XXX.', 'X.X..X.X.X.', 'X......X.X.', 'X..X...XXX.', 'X......X...', '.XXXXXX....', 'XXXXXXXXX..'],
  glocke: ['.....X.....', '....XXX....', '...XXXXX...', '..XXXXXXX..', '..XXXXXXX..', '..XXXXXXX..', '.XXXXXXXXX.', '.XXXXXXXXX.', 'XXXXXXXXXXX', '...........', '....XXX....', '.....X.....'],
  geschenk: ['..XX...XX..', '.X..X.X..X.', '..XXXXXXX..', 'XXXXXXXXXXX', 'X....X....X', 'XXXXXXXXXXX', '.X...X...X.', '.X...X...X.', '.X...X...X.', '.X...X...X.', '.XXXXXXXXX.', '...........'],
  schneeflocke: ['.....X.....', '...X.X.X...', '....XXX....', '.X...X...X.', '..X..X..X..', 'XXXXXXXXXXX', '..X..X..X..', '.X...X...X.', '....XXX....', '...X.X.X...', '.....X.....', '...........'],
  kugel: ['....XXX....', '....X.X....', '...XXXXX...', '..X.....X..', '.X.......X.', '.XXXXXXXXX.', '.X.X.X.X.X.', '.XXXXXXXXX.', '.X.......X.', '..X.....X..', '...XXXXX...', '...........'],
  herz: ['.....X.....', '....X.X....', '...X...X...', '.XX.....XX.', 'XXXX...XXXX', 'XXXXX.XXXXX', 'XX.XXXXX.XX', '.XXXXXXXXX.', '..XX.X.XX..', '...XXXXX...', '....XXX....', '.....X.....'],
  kirche: ['.....X.....', '....XXX....', '.....X.....', '....XXX....', '....X.X....', '...XXXXX...', '..XXXXXXX..', '.XXXXXXXXX.', '.X.X...X.X.', '.X.X.X.X.X.', '.X...X...X.', 'XXXXXXXXXXX'],
  turm: ['..X.X.X.X..', '..XXXXXXX..', '...X...X...', '...X.X.X...', '...X...X...', '...XXXXX...', '...X...X...', '...X.X.X...', '...X...X...', '..XXXXXXX..', '..X..X..X..', 'XXXXXXXXXXX'],
  rathaus: ['.....X.....', '....XXX....', '....X.X....', '...XXXXX...', 'XXXXXXXXXXX', 'X.X.X.X.X.X', 'XXXXXXXXXXX', 'X.X.X.X.X.X', 'XXXXXXXXXXX', 'X.X.XXX.X.X', 'XXXXX.XXXXX', '...........'],
  // The contact page's mark; no occasion rule picks it.
  brief: ['...........', '...........', 'XXXXXXXXXXX', 'XX.......XX', 'X.X.....X.X', 'X..X...X..X', 'X...X.X...X', 'X....X....X', 'X.........X', 'X.........X', 'XXXXXXXXXXX', '...........'],
} as const;

export type PictogramName = keyof typeof PICTOGRAMS;

// The source has no category per occasion (#39/#25). A clear word in the
// official name picks a specific pictogram; every other occasion gets one from
// the Advent set, seeded by its name so it never changes between builds.
// A pictogram is decoration, never a fact: change a rule, never add per-slug
// overrides.
const RULES: Array<[RegExp, PictogramName]> = [
  [/pyramide/i, 'pyramide'],
  [/lichter|licht|lights/i, 'laterne'],
  [/rathaus/i, 'rathaus'],
  [/kirche\b/i, 'kirche'],
  [/\bturm\b/i, 'turm'],
  [/festival|konzert|open air/i, 'note'],
  [/kürbis|kurbis|apfel|ernte|hoffest/i, 'kuerbis'],
  [/feuerwerk/i, 'feuer'],
  [/garten|gärten|illumination/i, 'fontaene'],
  [/oktoberfest|schützenfest|wiesn|frühlingsfest/i, 'rad'],
];

export const ADVENT_SET: readonly PictogramName[] = [
  'stand', 'tasse', 'glocke', 'geschenk', 'schneeflocke', 'kugel', 'herz', 'baum', 'stern', 'kerze',
];

function seed(text: string): number {
  let hash = 2166136261;
  for (const char of text) hash = Math.imul(hash ^ char.codePointAt(0)!, 16777619);
  return hash >>> 0;
}

export function occasionPictogram(occasion: Pick<OccasionSummary, 'name'>): PictogramName {
  return RULES.find(([pattern]) => pattern.test(occasion.name))?.[1] ??
    ADVENT_SET[seed(occasion.name) % ADVENT_SET.length];
}

/** The dots alone, placed at x/y, for embedding in a larger SVG (share posters). */
export function pictogramDots(
  name: PictogramName,
  step: number,
  { fill = 'currentColor', x = 0, y = 0 }: { fill?: string; x?: number; y?: number } = {},
): string {
  // Below a 4 px pitch the unlit dots turn into grey noise, so small icons drop them.
  const showUnlit = step >= 4;
  return PICTOGRAMS[name].flatMap((row, r) => [...row].map((cell, c) => {
    const lit = cell === 'X';
    if (!lit && !showUnlit) return '';
    const radius = step * (lit && !showUnlit ? 0.46 : 0.38);
    return `<circle cx="${x + c * step + step / 2}" cy="${y + r * step + step / 2}" r="${radius}" fill="${fill}"${lit ? '' : ' opacity="0.13"'}/>`;
  })).join('');
}

/** Inline SVG; lit dots use currentColor. */
export function pictogramSvg(name: PictogramName, step: number): string {
  const rows = PICTOGRAMS[name];
  const width = rows[0].length * step;
  const height = rows.length * step;
  return `<svg class="px" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" aria-hidden="true" focusable="false">${pictogramDots(name, step)}</svg>`;
}
