/**
 * Calendar arithmetic on ISO dates (YYYY-MM-DD), in UTC so a
 * day is the same day in every timezone.
 */

export const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export const WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"];

export function toIso(date) {
  return date.toISOString().slice(0, 10);
}

export function fromIso(iso) {
  return new Date(`${iso}T00:00:00Z`);
}

export function addDays(iso, days) {
  const date = fromIso(iso);
  date.setUTCDate(date.getUTCDate() + days);
  return toIso(date);
}

export function isWeekend(iso) {
  const day = fromIso(iso).getUTCDay();
  return day === 0 || day === 6;
}

/** The last weekday on or before `iso`. */
export function lastWeekday(iso) {
  let day = iso;
  while (isWeekend(day)) day = addDays(day, -1);
  return day;
}

/** { year, month } of an ISO date; month is 0-based. */
export function monthOf(iso) {
  const date = fromIso(iso);
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() };
}

export function shiftMonth({ year, month }, by) {
  const date = new Date(Date.UTC(year, month + by, 1));
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() };
}

/**
 * The six rows of a month grid, Monday first: 42 ISO dates,
 * the leading and trailing ones belonging to the neighbours.
 */
export function monthGrid({ year, month }) {
  const first = new Date(Date.UTC(year, month, 1));
  const lead = (first.getUTCDay() + 6) % 7;
  const start = addDays(toIso(first), -lead);

  return Array.from({ length: 42 }, (_, index) => addDays(start, index));
}

/**
 * The sessions the desk may replay: the year up to the latest
 * session, weekdays only. Both bounds are ISO dates.
 */
export function replayBounds(latestSession) {
  const max = lastWeekday(latestSession);
  return { min: addDays(max, -365), max };
}
