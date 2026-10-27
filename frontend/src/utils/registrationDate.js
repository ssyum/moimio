const DATE_INPUT_PATTERN = /^(\d{2})\.(\d{2})\.(\d{4})$/;
const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

const isValidDate = (year, month, day) => {
  const date = new Date(0);
  date.setUTCHours(0, 0, 0, 0);
  date.setUTCFullYear(year, month - 1, day);
  return date.getUTCFullYear() === year
    && date.getUTCMonth() === month - 1
    && date.getUTCDate() === day;
};

export function parseRegistrationDate(value) {
  const input = String(value ?? '').trim();
  const inputMatch = DATE_INPUT_PATTERN.exec(input);
  const isoMatch = ISO_DATE_PATTERN.exec(input);
  const match = inputMatch || isoMatch;
  if (!match) return null;

  const year = Number(inputMatch ? match[3] : match[1]);
  const month = Number(match[2]);
  const day = Number(inputMatch ? match[1] : match[3]);
  if (!isValidDate(year, month, day)) return null;

  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

export function formatRegistrationDate(value) {
  const iso = parseRegistrationDate(value);
  if (!iso) return String(value ?? '');
  const [year, month, day] = iso.split('-');
  return `${day}.${month}.${year}`;
}
