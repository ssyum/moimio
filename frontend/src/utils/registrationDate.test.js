import { describe, expect, it } from 'vitest';
import { formatRegistrationDate, parseRegistrationDate } from './registrationDate';

describe('registration date format', () => {
  it('converts the displayed day-first format to ISO', () => {
    expect(parseRegistrationDate('31.12.2000')).toBe('2000-12-31');
  });

  it('accepts ISO dates from existing saved form drafts', () => {
    expect(parseRegistrationDate('2000-12-31')).toBe('2000-12-31');
  });

  it('rejects impossible dates and incomplete input', () => {
    expect(parseRegistrationDate('31.02.2000')).toBeNull();
    expect(parseRegistrationDate('31.12.')).toBeNull();
  });

  it('formats valid ISO dates for display and preserves unfinished input', () => {
    expect(formatRegistrationDate('2000-12-31')).toBe('31.12.2000');
    expect(formatRegistrationDate('31.12.')).toBe('31.12.');
  });
});
