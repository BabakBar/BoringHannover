import { describe, expect, test } from 'bun:test';
import {
  correctionHref,
  fallbackMailto,
  interpretResponse,
  mapFieldErrors,
  prefillFromQuery,
  sentEvent,
  validateLocally,
} from './kontakt';

describe('prefillFromQuery', () => {
  test.each([
    ['no query', '', { kind: 'kontakt', context: '', page: '' }],
    ['correction deep link', '?art=korrektur&bezug=Kunst%20%26%20K%C3%BCrbis&seite=%2Fspecial%2Fwiesn%2F', { kind: 'korrektur', context: 'Kunst & Kürbis', page: '/special/wiesn/' }],
    ['suggestion', '?art=vorschlag', { kind: 'vorschlag', context: '', page: '' }],
    ['unknown kind falls back to general', '?art=admin', { kind: 'kontakt', context: '', page: '' }],
    ['absolute URL is not a page on this site', '?seite=https%3A%2F%2Fevil.example%2F', { kind: 'kontakt', context: '', page: '' }],
    ['protocol-relative URL is dropped', '?seite=%2F%2Fevil.example', { kind: 'kontakt', context: '', page: '' }],
    ['line breaks in the context collapse', '?bezug=a%0D%0Ab', { kind: 'kontakt', context: 'a b', page: '' }],
    ['context is cut to the endpoint limit', `?bezug=${'x'.repeat(600)}`, { kind: 'kontakt', context: 'x'.repeat(500), page: '' }],
  ])('%s', (_name, search, expected) => {
    expect(prefillFromQuery(search)).toEqual(expected);
  });
});

test('correctionHref round-trips through the prefill', () => {
  const title = 'Kunst & Kürbis: „Herbst“ #2';
  const href = correctionHref(title, '/special/kunst-kuerbis/');
  expect(href.startsWith('/kontakt/?art=korrektur&')).toBe(true);
  expect(prefillFromQuery(href.slice('/kontakt/'.length))).toEqual({
    kind: 'korrektur',
    context: title,
    page: '/special/kunst-kuerbis/',
  });
});

describe('endpoint errors', () => {
  test('422 fields map to English messages and unknown fields are ignored', () => {
    expect(interpretResponse(422, { ok: false, error: 'invalid', fields: { email: 'invalid', message: 'too_short', honeypot: 'invalid' } })).toEqual({
      type: 'invalid',
      fields: {
        email: "That doesn't look like a valid email address, e.g. name@example.com.",
        message: 'Please write at least 2 characters.',
      },
    });
  });

  test.each([
    [200, { ok: true, id: 'x' }, 'sent'],
    [403, { error: 'challenge' }, 'challenge'],
    [403, { error: 'origin' }, 'unavailable'],
    [413, { error: 'too_large' }, 'unavailable'],
    [503, { error: 'unavailable' }, 'unavailable'],
    [500, null, 'unavailable'],
    [200, null, 'unavailable'],
  ])('status %d %j → %s', (status, body, type) => {
    expect(interpretResponse(status, body).type).toBe(type);
  });

  test('errors on fields the form does not show are dropped, so the caller falls back to e-mail', () => {
    const fields = mapFieldErrors({ message: 'required', name: 'too_long', kind: 'invalid', context: 'too_long' });
    expect(fields).toEqual({
      message: 'Please enter your message.',
      name: 'Your name is too long (max 120 characters).',
    });
  });
});

describe('fallbackMailto carries what was typed', () => {
  test.each([
    ['nothing typed', '', '', 'mailto:kontakt@boringhannover.de'],
    ['message only', ' Beginn 19 Uhr \n', '', 'mailto:kontakt@boringhannover.de?body=Beginn%2019%20Uhr'],
    ['message and reference', 'a+b & c', 'Kunst & Kürbis', 'mailto:kontakt@boringhannover.de?subject=Kunst%20%26%20K%C3%BCrbis&body=a%2Bb%20%26%20c'],
  ])('%s', (_name, message, context, href) => {
    expect(fallbackMailto(message, context)).toBe(href);
  });
});

describe('validateLocally mirrors the Worker', () => {
  test('a valid form passes', () => {
    expect(validateLocally('a@b.de', 'Hallo', '')).toEqual({});
  });

  test.each([
    ['blank email and message', '  ', '', ['email', 'message'], ''],
    ['email without a dot after the @', 'a@b', 'Hallo', ['email'], ''],
    ['one-character message', 'a@b.de', 'x', ['message'], ''],
    ['message over 5000 characters', 'a@b.de', 'x'.repeat(5001), ['message'], ''],
    ['name over 120 characters', 'a@b.de', 'Hallo', ['name'], 'x'.repeat(121)],
  ])('%s', (_name, email, message, fields, name) => {
    expect(Object.keys(validateLocally(email, message, name)).sort()).toEqual(fields);
  });
});

test('the analytics event carries the kind and nothing the visitor typed', () => {
  expect(sentEvent('vorschlag')).toEqual({ name: 'contact-sent', data: { kind: 'vorschlag' } });
});
