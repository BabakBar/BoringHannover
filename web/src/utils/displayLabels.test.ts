import { expect, test } from 'bun:test';
import {
  explainAdmissionLabel,
  formatEventTime,
  formatFskRating,
} from './displayLabels';

test('formatEventTime shows the German end-of-day 24:00 as midnight', () => {
  expect(formatEventTime('24:00')).toBe('midnight');
  expect(formatEventTime('20:00')).toBe('20:00');
  expect(formatEventTime('00:30')).toBe('00:30');
});

test('formatFskRating adds a space and a plus, keeping unknown ratings', () => {
  expect(formatFskRating('FSK12')).toBe('FSK 12+');
  expect(formatFskRating('FSK 6')).toBe('FSK 6+');
  expect(formatFskRating('ohne Angabe')).toBe('ohne Angabe');
});

test('explainAdmissionLabel explains reviewed entry rows and guesses nothing else', () => {
  expect(explainAdmissionLabel('Erwachsene')).toEqual({
    english: 'Adults',
    keepOriginal: false,
  });
  expect(explainAdmissionLabel('Kinder (bis 14 Jahre)')?.english).toBe(
    'Children up to age 14',
  );
  expect(explainAdmissionLabel('Kinder bis 6 Jahren')?.english).toBe(
    'Children up to age 6',
  );
  expect(explainAdmissionLabel('Kinder')?.english).toBe('Children');
  // The German term is what the gate uses, so it stays beside the English.
  expect(
    explainAdmissionLabel('Mit Baumscheibe (für Eichel- und Kastaniensammler*innen)'),
  ).toEqual({
    english: 'With a tree slice, for acorn and chestnut collectors',
    keepOriginal: true,
  });
  expect(explainAdmissionLabel('Mit Gästekarte')).toBeNull();
  expect(explainAdmissionLabel('Erwachsene mit Hund')).toBeNull();
});
