function dateKey(value, timeZone) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  let parts;
  try {
    parts = new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      ...(timeZone ? { timeZone } : {}),
    }).formatToParts(date);
  } catch {
    parts = new Intl.DateTimeFormat('en-CA', {
      year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(date);
  }
  const part = (type) => parts.find(item => item.type === type)?.value;
  const year = part('year');
  const month = part('month');
  const day = part('day');
  return year && month && day ? `${year}-${month}-${day}` : null;
}

function dayNumber(key) {
  if (!key) return null;
  const [year, month, day] = key.split('-').map(Number);
  return Date.UTC(year, month - 1, day) / 86_400_000;
}

export function calendarDateKey(value, timeZone) {
  return dateKey(value, timeZone);
}

export function daysSinceRegistration(registeredAt, timeZone, now = new Date()) {
  const registeredDay = dayNumber(dateKey(registeredAt, timeZone));
  const currentDay = dayNumber(dateKey(now, timeZone));
  if (registeredDay === null || currentDay === null) return null;
  return Math.max(0, currentDay - registeredDay);
}

export function registrationAgeTier(days, registrationStatus) {
  if (registrationStatus === 'confirmed') return 'confirmed';
  if (days > 7) return 'overdue';
  if (days >= 4) return 'reminder';
  return 'recent';
}
