import { describe, expect, test } from 'bun:test';
import { getCinemaLabel } from './cinemaLabel';

describe('getCinemaLabel', () => {
  test('uses compact labels for the current Hannover cinemas', () => {
    expect(getCinemaLabel('Astor Grand Cinema')).toBe('Astor');
    expect(getCinemaLabel('Apollokino Hannover')).toBe('Apollo');
  });

  test('keeps a future cinema name instead of hiding it', () => {
    expect(getCinemaLabel('Kino am Raschplatz')).toBe('Kino am Raschplatz');
  });

  test('omits the label for older feeds without venue data', () => {
    expect(getCinemaLabel(undefined)).toBeNull();
  });
});
