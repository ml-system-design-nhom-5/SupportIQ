/**
 * The shared duration formatters (UI-29): a duration that `backend` measured, such as a latency or
 * a handling time of a report, written as the mockups write it ("3.6 s", "2 min 10 s"), and a
 * latency of the developer details in milliseconds ("3,420 ms").
 */
import { formatCount, formatOneDecimal } from "@/design-system/format/number";

const MILLISECONDS_PER_SECOND = 1000;
const MILLISECONDS_PER_TENTH_OF_SECOND = 100;
const TENTHS_PER_SECOND = 10;
const SECONDS_PER_MINUTE = 60;
const TENTHS_PER_MINUTE = SECONDS_PER_MINUTE * TENTHS_PER_SECOND;

/** The width of the seconds after the minutes, as in "3 min 05 s" of the mockups. */
const SECONDS_WIDTH = 2;

/** How a duration is rounded to the precision it is shown with. */
const roundingByMode: Readonly<Record<DurationRounding, (value: number) => number>> = {
  nearest: Math.round,
  up: Math.ceil,
};

/**
 * How a duration is rounded: `nearest` by default; `up` next to a target of at most some time,
 * so a figure just above the target never shows as the target itself ("12.1 s", not "12 s", for
 * 12 040 ms next to "At most 12 s").
 */
export type DurationRounding = "nearest" | "up";

/**
 * Format a duration: seconds with one decimal under a minute, otherwise minutes and whole seconds.
 *
 * @param durationMs - A duration from `backend`, in milliseconds (CODE-03).
 * @param rounding - How to round to the precision shown; to the nearest by default.
 * @returns For example `3.6 s`, `4 s`, `3 min 05 s`, or `17 min 30 s`.
 */
export function formatDuration(durationMs: number, rounding: DurationRounding = "nearest"): string {
  const round = roundingByMode[rounding];
  const tenths = round(durationMs / MILLISECONDS_PER_TENTH_OF_SECOND);
  if (tenths < TENTHS_PER_MINUTE) {
    return `${formatOneDecimal(tenths / TENTHS_PER_SECOND)} s`;
  }
  const seconds = round(durationMs / MILLISECONDS_PER_SECOND);
  const minutes = formatCount(Math.floor(seconds / SECONDS_PER_MINUTE));
  const restSeconds = String(seconds % SECONDS_PER_MINUTE).padStart(SECONDS_WIDTH, "0");
  return `${minutes} min ${restSeconds} s`;
}

/**
 * Format a duration in milliseconds as `backend` sent it, for the developer details (UI-35).
 *
 * @param durationMs - A duration from `backend`, in milliseconds.
 * @returns For example `3,420 ms`.
 */
export function formatMilliseconds(durationMs: number): string {
  return `${formatCount(durationMs)} ms`;
}
