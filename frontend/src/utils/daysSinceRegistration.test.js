import { describe, expect, it } from 'vitest';
import {
  calendarDateKey,
  daysSinceRegistration,
  registrationAgeTier,
} from './daysSinceRegistration';

describe('days since registration', () => {
  it('counts calendar days in the event timezone, with registration day as day zero', () => {
    expect(daysSinceRegistration(
      '2026-03-28T22:30:00Z',
      'Europe/Berlin',
      new Date('2026-03-31T00:30:00Z'),
    )).toBe(3);
  });

  it('counts a partial elapsed day as the same calendar day', () => {
    expect(daysSinceRegistration(
      '2026-03-28T10:00:00Z',
      'UTC',
      new Date('2026-03-28T23:59:00Z'),
    )).toBe(0);
  });

  it('counts the payment reminder boundaries as four, seven, and eight days', () => {
    const registration = '2026-03-01T12:00:00Z';
    expect(daysSinceRegistration(registration, 'UTC', new Date('2026-03-05T00:00:00Z'))).toBe(4);
    expect(daysSinceRegistration(registration, 'UTC', new Date('2026-03-08T00:00:00Z'))).toBe(7);
    expect(daysSinceRegistration(registration, 'UTC', new Date('2026-03-09T00:00:00Z'))).toBe(8);
  });

  it('does not return a negative value for a future registration timestamp', () => {
    expect(daysSinceRegistration(
      '2026-03-29T00:00:00Z',
      'UTC',
      new Date('2026-03-28T23:59:00Z'),
    )).toBe(0);
  });

  it('returns a null key for an invalid timestamp', () => {
    expect(calendarDateKey('not-a-date', 'UTC')).toBeNull();
  });

  it('uses the requested status and day thresholds for the counter colour', () => {
    expect(registrationAgeTier(3, 'pending')).toBe('recent');
    expect(registrationAgeTier(4, 'pending')).toBe('reminder');
    expect(registrationAgeTier(7, 'pending')).toBe('reminder');
    expect(registrationAgeTier(8, 'pending')).toBe('overdue');
    expect(registrationAgeTier(20, 'confirmed')).toBe('confirmed');
    expect(registrationAgeTier(20, 'paid')).toBe('confirmed');
  });
});
