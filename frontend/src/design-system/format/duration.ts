/**
 * The shared duration formatter (UI-29): a duration that `backend` measured, such as a latency or
 * a handling time of a report, written as the mockups write it ("3.6 s", "2 min 10 s").
 */

const MILLISECONDS_PER_SECOND = 1000;
const MILLISECONDS_PER_TENTH_OF_SECOND = 100;
const TENTHS_PER_SECOND = 10;
const SECONDS_PER_MINUTE = 60;
const TENTHS_PER_MINUTE = SECONDS_PER_MINUTE * TENTHS_PER_SECOND;

/** The width of the seconds after the minutes, as in "3 min 05 s" of the mockups. */
const SECONDS_WIDTH = 2;

/** The locale of the numbers in the mockups. */
const NUMBER_LOCALE = "en-US";

/** Seconds under a minute with one decimal at most: "3.6 s", "4 s". */
const secondsFormatter = new Intl.NumberFormat(NUMBER_LOCALE, { maximumFractionDigits: 1 });

/** Whole minutes with a thousands separator. */
const minutesFormatter = new Intl.NumberFormat(NUMBER_LOCALE, { maximumFractionDigits: 0 });

/**
 * Format a duration: seconds with one decimal under a minute, otherwise minutes and whole seconds.
 *
 * @param durationMs - A duration from `backend`, in milliseconds (CODE-03).
 * @returns For example `3.6 s`, `4 s`, `3 min 05 s`, or `17 min 30 s`.
 */
export function formatDuration(durationMs: number): string {
  const tenths = Math.round(durationMs / MILLISECONDS_PER_TENTH_OF_SECOND);
  if (tenths < TENTHS_PER_MINUTE) {
    return `${secondsFormatter.format(tenths / TENTHS_PER_SECOND)} s`;
  }
  const seconds = Math.round(durationMs / MILLISECONDS_PER_SECOND);
  const minutes = minutesFormatter.format(Math.floor(seconds / SECONDS_PER_MINUTE));
  const restSeconds = String(seconds % SECONDS_PER_MINUTE).padStart(SECONDS_WIDTH, "0");
  return `${minutes} min ${restSeconds} s`;
}
