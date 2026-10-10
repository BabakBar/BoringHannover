import { expect, test } from 'bun:test';
import { getCinemaLabel } from './cinemaLabel';

test('getCinemaLabel shortens known cinemas and keeps unknown ones', () => {
  expect(getCinemaLabel('Astor Grand Cinema')).toBe('Astor');
  expect(getCinemaLabel('Apollokino Hannover')).toBe('Apollo');
  expect(getCinemaLabel('Kino am Raschplatz')).toBe('Kino am Raschplatz');
  // Older feeds without venue data.
  expect(getCinemaLabel(undefined)).toBeNull();
});
