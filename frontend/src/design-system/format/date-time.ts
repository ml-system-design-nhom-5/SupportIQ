/**
 * The shared date and time formatters (UI-29). Times show a relative value, with the absolute
 * local time on hover; dates use the day-month-year format of the mockups ("2 Oct 2026").
 */

/** The locale of dates and times in the mockups. */
const DATE_LOCALE = "en-GB";
/** The locale of relative times: "3 weeks ago". */
const RELATIVE_TIME_LOCALE = "en";

const MILLISECONDS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;
const MINUTES_PER_HOUR = 60;
const HOURS_PER_DAY = 24;
const DAYS_PER_WEEK = 7;
const DAYS_PER_MONTH = 30;
const DAYS_PER_YEAR = 365;

const dateFormatter = new Intl.DateTimeFormat(DATE_LOCALE, { dateStyle: "medium" });
const dateTimeFormatter = new Intl.DateTimeFormat(DATE_LOCALE, {
  dateStyle: "medium",
  timeStyle: "short",
});
const relativeTimeFormatter = new Intl.RelativeTimeFormat(RELATIVE_TIME_LOCALE, {
  numeric: "always",
});

/**
 * Format the local date of a timestamp.
 *
 * @param timestamp - An RFC 3339 timestamp (CON-17).
 * @returns The date, for example `2 Oct 2026`.
 */
export function formatDate(timestamp: string): string {
  return dateFormatter.format(new Date(timestamp));
}

/**
 * Format the local date and time of a timestamp.
 *
 * @param timestamp - An RFC 3339 timestamp.
 * @returns The date and time, for example `2 Oct 2026, 19:30`.
 */
export function formatDateTime(timestamp: string): string {
  return dateTimeFormatter.format(new Date(timestamp));
}

/**
 * Format how long ago a timestamp was.
 *
 * @param timestamp - An RFC 3339 timestamp.
 * @param now - The current time, from the clock of the caller (CODE-18).
 * @returns `Just now` under a minute, or in the future, otherwise for example `3 weeks ago`.
 */
export function formatRelativeTime(timestamp: string, now: Date): string {
  const elapsedSeconds = (now.getTime() - new Date(timestamp).getTime()) / MILLISECONDS_PER_SECOND;
  const elapsedMinutes = Math.floor(elapsedSeconds / SECONDS_PER_MINUTE);
  if (elapsedMinutes < 1) {
    return "Just now";
  }
  const elapsedHours = Math.floor(elapsedMinutes / MINUTES_PER_HOUR);
  if (elapsedHours < 1) {
    return relativeTimeFormatter.format(-elapsedMinutes, "minute");
  }
  const elapsedDays = Math.floor(elapsedHours / HOURS_PER_DAY);
  if (elapsedDays < 1) {
    return relativeTimeFormatter.format(-elapsedHours, "hour");
  }
  return formatElapsedDays(elapsedDays);
}

/**
 * Format a number of whole days ago in the largest fitting unit.
 *
 * @param elapsedDays - At least one day.
 * @returns For example `2 days ago`, `3 weeks ago`, `4 months ago`, or `1 year ago`.
 */
function formatElapsedDays(elapsedDays: number): string {
  if (elapsedDays < DAYS_PER_WEEK) {
    return relativeTimeFormatter.format(-elapsedDays, "day");
  }
  if (elapsedDays < DAYS_PER_MONTH) {
    return relativeTimeFormatter.format(-Math.floor(elapsedDays / DAYS_PER_WEEK), "week");
  }
  if (elapsedDays < DAYS_PER_YEAR) {
    return relativeTimeFormatter.format(-Math.floor(elapsedDays / DAYS_PER_MONTH), "month");
  }
  return relativeTimeFormatter.format(-Math.floor(elapsedDays / DAYS_PER_YEAR), "year");
}
