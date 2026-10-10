import { expect, test } from 'bun:test';
import { facts } from './hannover';

test('there are enough facts to rotate, each short and distinct', () => {
  expect(facts.length).toBeGreaterThanOrEqual(5);
  expect(new Set(facts).size).toBe(facts.length);
  for (const fact of facts) {
    expect(fact.length).toBeGreaterThan(20);
    expect(fact.length).toBeLessThanOrEqual(110);
  }
});

test('the city is more than Leibniz: club, tyres and vans get a line too', () => {
  const text = facts.join(' ');
  for (const name of ['Hannover 96', 'Continental', 'Transporter']) expect(text).toContain(name);
});
