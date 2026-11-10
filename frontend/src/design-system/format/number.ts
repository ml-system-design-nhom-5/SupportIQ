/**
 * The shared number formatter (UI-29): counts with a thousands separator, as in "2,000".
 */

/** The locale of numbers in the mockups: "0 / 2,000 characters". */
const NUMBER_LOCALE = "en-US";

const countFormatter = new Intl.NumberFormat(NUMBER_LOCALE, { maximumFractionDigits: 0 });

/**
 * Format a count for display.
 *
 * @param count - A whole number.
 * @returns For example `2,000`.
 */
export function formatCount(count: number): string {
  return countFormatter.format(count);
}
