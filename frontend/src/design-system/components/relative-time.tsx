/**
 * A relative time, with the absolute local time on hover, focus, or tap (UI-29).
 */
import { useNow } from "@/design-system/format/clock";
import { formatDateTime, formatRelativeTime } from "@/design-system/format/date-time";
import { Tooltip } from "@/design-system/primitives/tooltip";

/** Props of {@link RelativeTime}. */
export type RelativeTimeProps = {
  /** An RFC 3339 timestamp (CON-17). */
  readonly timestamp: string;
};

/**
 * Render how long ago something happened.
 *
 * @param props - The timestamp.
 * @returns For example `3 weeks ago`, with `2 Oct 2026, 19:30` in its tooltip.
 */
export function RelativeTime({ timestamp }: RelativeTimeProps) {
  const now = useNow();
  return (
    <Tooltip content={formatDateTime(timestamp)}>
      <time dateTime={timestamp}>{formatRelativeTime(timestamp, now)}</time>
    </Tooltip>
  );
}
