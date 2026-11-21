/**
 * The values of a report with their units (UI-44): counts of tickets, replies, escalations, and
 * suggestions, and the text of a figure that `backend` left out because nothing was counted. The
 * numbers go through the shared formatters (UI-29); the UI computes no figure (UI-14).
 */
import { formatCount } from "@/design-system";

/** What a share, a percentile, or an average says when `backend` left it out. */
export const NO_DATA_TEXT = "No data";

/** The singular and the plural of each counted thing. */
const nounsByUnit: Readonly<
  Record<CountUnit, { readonly singular: string; readonly plural: string }>
> = {
  ticket: { singular: "ticket", plural: "tickets" },
  reply: { singular: "reply", plural: "replies" },
  escalation: { singular: "escalation", plural: "escalations" },
  suggestion: { singular: "suggestion", plural: "suggestions" },
};

/** What a count of the report counts. */
export type CountUnit = "ticket" | "reply" | "escalation" | "suggestion";

/**
 * Format a count with its unit.
 *
 * @param count - A whole number from `backend`.
 * @param unit - What it counts.
 * @returns For example `1 ticket` or `1,200 tickets`.
 */
export function formatCountOf(count: number, unit: CountUnit): string {
  const nouns = nounsByUnit[unit];
  return `${formatCount(count)} ${count === 1 ? nouns.singular : nouns.plural}`;
}

/**
 * Format a figure that `backend` leaves out when nothing was counted, such as a share, a
 * percentile, or an average.
 *
 * @param value - The figure, or undefined when `backend` left it out.
 * @param format - Formats a figure that is there.
 * @returns The formatted figure, or {@link NO_DATA_TEXT}.
 */
export function formatOptional(
  value: number | undefined,
  format: (value: number) => string,
): string {
  return value === undefined ? NO_DATA_TEXT : format(value);
}
