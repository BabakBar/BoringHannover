import { describe, expect, test } from 'bun:test';
import { occasionSourceLink } from './occasionSource';

describe('occasionSourceLink', () => {
  test('the city calendar is a listing, not the organiser', () => {
    for (const url of [
      'https://www.hannover.de/Veranstaltungskalender/Feste-Festivals/Tiergartenfest-Hannover',
      'https://hannover.de/Veranstaltungskalender/Feste-Festivals/KiezKultur-Festival',
      'https://WWW.HANNOVER.DE/Veranstaltungskalender/Feste-Festivals/X',
    ]) {
      expect(occasionSourceLink(url)?.label).toBe('Listing on hannover.de');
    }
  });

  test('an organiser source keeps its official website label', () => {
    expect(
      occasionSourceLink('https://www.maschseefest.de/veranstaltungen/'),
    ).toEqual({
      url: 'https://www.maschseefest.de/veranstaltungen/',
      label: 'Official website',
    });
  });

  test('the label follows the parsed host, not text in the URL', () => {
    for (const url of [
      'https://www.hannover.de.example.com/Veranstaltungskalender/',
      'https://www.hannover.de@example.com/Veranstaltungskalender/',
      'https://example.com/www.hannover.de/Veranstaltungskalender/',
    ]) {
      expect(occasionSourceLink(url)?.label).not.toBe('Listing on hannover.de');
    }
  });

  test('unsafe or unparseable URLs give no link', () => {
    for (const url of [
      undefined,
      '',
      'javascript:alert(1)',
      'data:text/html,<script>alert(1)</script>',
      'https://',
    ]) {
      expect(occasionSourceLink(url)).toBeNull();
    }
  });
});
