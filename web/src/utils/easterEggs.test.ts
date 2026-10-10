import { describe, expect, test } from 'bun:test';
import { KONAMI, NINETY_SIX, countAt, konamiStep, sequenceStep, toBinary } from './easterEggs';

describe('toBinary', () => {
  test('writes a count the way Leibniz would', () => {
    expect(toBinary(0)).toBe('0');
    expect(toBinary(4)).toBe('100');
    expect(toBinary(13)).toBe('1101');
  });
});

describe('konamiStep', () => {
  const press = (keys: string[]) => keys.reduce(konamiStep, 0);

  test('completes on the full sequence', () => {
    expect(press([...KONAMI])).toBe(KONAMI.length);
  });

  test('ignores the case of letter keys', () => {
    expect(press([...KONAMI.slice(0, -2), 'B', 'A'])).toBe(KONAMI.length);
  });

  test('a wrong key starts over', () => {
    expect(press(['ArrowUp', 'ArrowUp', 'x'])).toBe(0);
  });

  test('a wrong key that is also the first key counts as a fresh start', () => {
    expect(press(['ArrowUp', 'ArrowUp', 'ArrowUp'])).toBe(2);
    expect(press(['ArrowUp', 'ArrowDown'])).toBe(0);
  });
});

describe('sequenceStep', () => {
  const press = (keys: string[]) => keys.reduce((progress, key) => sequenceStep(NINETY_SIX, progress, key), 0);

  test('typing 96 completes it', () => {
    expect(press(['9', '6'])).toBe(NINETY_SIX.length);
  });

  test('996 still completes it, 69 does not', () => {
    expect(press(['9', '9', '6'])).toBe(NINETY_SIX.length);
    expect(press(['6', '9'])).toBe(1);
  });
});

describe('countAt', () => {
  test('runs from 0 to the target and never overshoots', () => {
    expect(countAt(0, 107)).toBe(0);
    expect(countAt(1, 107)).toBe(107);
    expect(countAt(2, 107)).toBe(107);
  });

  test('only ever goes up', () => {
    let last = -1;
    for (let t = 0; t <= 1; t += 0.05) {
      const value = countAt(t, 107);
      expect(value).toBeGreaterThanOrEqual(last);
      last = value;
    }
  });
});
