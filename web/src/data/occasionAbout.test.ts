import { expect, test } from 'bun:test';
import { occasionAbout } from './occasionAbout';

test('reviewed Advent copy only applies to its listed edition and status', () => {
  const occasion = {
    id: 'hannover-festivals:magische-lichterwelten-im-zoo',
    startDate: '2026-11-17',
    endDate: '2027-02-02',
  };
  expect(occasionAbout(occasion)?.description).toContain('Last entry is at 21:00');
  expect(occasionAbout({ ...occasion, sourceStatus: 'scheduled' })).toEqual(occasionAbout(occasion));
  expect(occasionAbout({ ...occasion, endDate: '2027-02-03' })).toBeUndefined();
  expect(occasionAbout({ ...occasion, sourceStatus: 'cancelled' })).toBeUndefined();
  expect(occasionAbout({ ...occasion, id: 'elsewhere:magische-lichterwelten-im-zoo' })).toBeUndefined();
  expect(occasionAbout({
    ...occasion, startDate: '2027-11-17', endDate: '2028-02-02',
  })).toBeUndefined();
});
