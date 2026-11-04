export function ageOnEventDate(dateOfBirth, eventStartDate) {
  if (!dateOfBirth || !eventStartDate) return null;
  const dobMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateOfBirth);
  const eventMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(eventStartDate);
  if (!dobMatch || !eventMatch) return null;

  const [, birthYear, birthMonth, birthDay] = dobMatch.map(Number);
  const [, eventYear, eventMonth, eventDay] = eventMatch.map(Number);
  const birth = new Date(Date.UTC(birthYear, birthMonth - 1, birthDay));
  const event = new Date(Date.UTC(eventYear, eventMonth - 1, eventDay));
  if (
    birth.getUTCFullYear() !== birthYear || birth.getUTCMonth() !== birthMonth - 1
    || birth.getUTCDate() !== birthDay || event.getUTCFullYear() !== eventYear
    || event.getUTCMonth() !== eventMonth - 1 || event.getUTCDate() !== eventDay
    || birth > event
  ) return null;

  return eventYear - birthYear
    - (eventMonth < birthMonth || (eventMonth === birthMonth && eventDay < birthDay) ? 1 : 0);
}
