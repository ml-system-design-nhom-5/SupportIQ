/**
 * The shared number formatters (UI-29): counts with a thousands separator, as in "2,000", whole
 * percentages of probabilities, and the shares of a report with one decimal.
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

const percentFormatter = new Intl.NumberFormat(NUMBER_LOCALE, {
  style: "percent",
  maximumFractionDigits: 0,
});

/**
 * Format a share in [0, 1] as a whole percentage, such as a calibrated probability that `backend`
 * sent (UI-14: the UI only formats it).
 *
 * @param share - A number from 0 to 1.
 * @returns For example `91%`.
 */
export function formatPercent(share: number): string {
  return percentFormatter.format(share);
}

const shareOneDecimalFormatter = new Intl.NumberFormat(NUMBER_LOCALE, {
  style: "percent",
  maximumFractionDigits: 1,
});

/**
 * Format a share in [0, 1] that `backend` computed for a report, such as the approve share, as a
 * percentage with at most one decimal (UI-44: the UI only formats it). Probabilities use
 * {@link formatPercent} instead.
 *
 * @param share - A number from 0 to 1.
 * @returns For example `46.2%`, `25%`, or `1.8%`.
 */
export function formatShareOneDecimal(share: number): string {
  return shareOneDecimalFormatter.format(share);
}
