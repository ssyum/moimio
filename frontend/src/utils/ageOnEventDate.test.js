import { describe, expect, it } from 'vitest';
import { ageOnEventDate } from './ageOnEventDate';

describe('ageOnEventDate', () => {
  it('calculates age before or on a birthday at event start', () => {
    expect(ageOnEventDate('2008-11-05', '2026-11-04')).toBe(17);
    expect(ageOnEventDate('2008-11-04', '2026-11-04')).toBe(18);
  });

  it('handles month boundaries, leap birthdays, and invalid or missing dates', () => {
    expect(ageOnEventDate('2008-12-01', '2026-11-30')).toBe(17);
    expect(ageOnEventDate('2008-02-29', '2026-02-28')).toBe(17);
    expect(ageOnEventDate('2008-02-29', '2026-03-01')).toBe(18);
    expect(ageOnEventDate('2027-01-01', '2026-12-31')).toBeNull();
    expect(ageOnEventDate('not-a-date', '2026-12-31')).toBeNull();
    expect(ageOnEventDate(null, '2026-12-31')).toBeNull();
  });
});
