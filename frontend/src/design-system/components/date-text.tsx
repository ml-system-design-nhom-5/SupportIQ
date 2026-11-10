/**
 * A calendar date, formatted by the shared formatter (UI-29).
 */
import { formatDate } from "@/design-system/format/date-time";

/** Props of {@link DateText}. */
export type DateTextProps = {
  /** An RFC 3339 timestamp (CON-17). */
  readonly timestamp: string;
};

/**
 * Render a local date.
 *
 * @param props - The timestamp.
 * @returns A `time` element, for example `2 Oct 2026`.
 */
export function DateText({ timestamp }: DateTextProps) {
  return <time dateTime={timestamp}>{formatDate(timestamp)}</time>;
}
