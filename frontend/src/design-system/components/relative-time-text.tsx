/**
 * A relative time inside a link or a row, where a button cannot be nested. The absolute local time
 * shows on hover through `title` (UI-29). The page that the row opens shows the time again as
 * {@link RelativeTime}, which also answers a tap.
 */
import { useNow } from "@/design-system/format/clock";
import { formatDateTime, formatRelativeTime } from "@/design-system/format/date-time";

/** Props of {@link RelativeTimeText}. */
export type RelativeTimeTextProps = {
  /** An RFC 3339 timestamp (CON-17). */
  readonly timestamp: string;
};

/**
 * Render how long ago something happened, as text.
 *
 * @param props - The timestamp.
 * @returns A `time` element, for example `3 weeks ago`.
 */
export function RelativeTimeText({ timestamp }: RelativeTimeTextProps) {
  const now = useNow();
  return (
    <time dateTime={timestamp} title={formatDateTime(timestamp)}>
      {formatRelativeTime(timestamp, now)}
    </time>
  );
}
