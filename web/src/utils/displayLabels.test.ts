import { describe, expect, test } from 'bun:test';
import {
  explainAdmissionLabel,
  formatEventTime,
  formatFskRating,
} from './displayLabels';

describe('formatEventTime', () => {
  test('shows the German end-of-day 24:00 as midnight', () => {
    expect(formatEventTime('24:00')).toBe('midnight');
  });

  test('leaves ordinary times untouched', () => {
    expect(formatEventTime('20:00')).toBe('20:00');
    expect(formatEventTime('00:30')).toBe('00:30');
  });
});

describe('formatFskRating', () => {
  test('adds a space and a plus to the age limit', () => {
    expect(formatFskRating('FSK12')).toBe('FSK 12+');
    expect(formatFskRating('FSK16')).toBe('FSK 16+');
    expect(formatFskRating('FSK 6')).toBe('FSK 6+');
  });

  test('keeps an unrecognised rating as published', () => {
    expect(formatFskRating('ohne Angabe')).toBe('ohne Angabe');
  });
});

describe('explainAdmissionLabel', () => {
  test('explains the Tiergartenfest price rows in English', () => {
    expect(explainAdmissionLabel('Erwachsene')).toEqual({
      english: 'Adults',
      keepOriginal: false,
    });
    expect(explainAdmissionLabel('Kinder (bis 14 Jahre)')).toEqual({
      english: 'Children up to age 14',
      keepOriginal: false,
    });
    // The German term is what the gate uses, so it stays beside the English.
    expect(
      explainAdmissionLabel(
        'Mit Baumscheibe (für Eichel- und Kastaniensammler*innen)',
      ),
    ).toEqual({
      english: 'With a tree slice, for acorn and chestnut collectors',
      keepOriginal: true,
    });
  });

  test('age limits keep their number', () => {
    expect(explainAdmissionLabel('Kinder bis 6 Jahren')?.english).toBe(
      'Children up to age 6',
    );
    expect(explainAdmissionLabel('Kinder')?.english).toBe('Children');
  });

  test('an unreviewed condition is not guessed', () => {
    expect(explainAdmissionLabel('Mit Gästekarte')).toBeNull();
    expect(explainAdmissionLabel('Erwachsene mit Hund')).toBeNull();
  });
});
