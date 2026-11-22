import { expect, test } from 'bun:test';
import { ADVENT_SET, occasionPictogram, pictogramSvg } from './pictogram';

test.each([
  ['Erzgebirgische Pyramide am Kröpcke', 'pyramide'],
  ['Lichtermeer Seelze', 'laterne'],
  ['ZooLights', 'laterne'],
  ['Adventsmarkt am Neuen Rathaus', 'rathaus'],
  ['Weihnachtsmarkt an der Marktkirche', 'kirche'],
  ['Wintertreff am Lister Turm', 'turm'],
  ['Fairground Festival', 'note'],
  ['Kunst & Kürbis', 'kuerbis'],
  ['Feuerwerkswettbewerb Herrenhausen', 'feuer'],
  ['Illumination in den Herrenhäuser Gärten', 'fontaene'],
  ['Oktoberfest Hannover', 'rad'],
])('%s → %s', (name, expected) => {
  expect(occasionPictogram({ name })).toBe(expected);
});

test('an unmatched name gets a stable Advent icon', () => {
  const first = occasionPictogram({ name: 'Weihnachtsmarkt Bothfeld' });
  const second = occasionPictogram({ name: 'Adventsbasar Kleefeld' });
  expect(ADVENT_SET).toContain(first);
  expect(ADVENT_SET).toContain(second);
  expect(occasionPictogram({ name: 'Weihnachtsmarkt Bothfeld' })).toBe(first);
  expect(occasionPictogram({ name: 'Adventsbasar Kleefeld' })).toBe(second);
});

test.each([
  { id: 'unlit dots from a 4 px pitch', step: 5, unlit: true },
  { id: 'no unlit noise below 4 px', step: 3, unlit: false },
])('pictogramSvg: $id', ({ step, unlit }) => {
  const svg = pictogramSvg('stern', step);
  expect(svg).toContain(`viewBox="0 0 ${11 * step} ${12 * step}"`);
  expect(svg).toContain('aria-hidden="true" focusable="false"');
  expect(svg.includes('opacity="0.13"')).toBe(unlit);
});
