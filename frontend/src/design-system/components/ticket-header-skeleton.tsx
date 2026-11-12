/**
 * The ticket header while the ticket loads (UI-24; console UI design, state-loading.png).
 */
import { Skeleton } from "@/design-system/primitives/skeleton";

/**
 * Render the skeleton of the ticket header.
 *
 * @returns The placeholder row, hidden from assistive technology.
 */
export function TicketHeaderSkeleton() {
  return (
    <div
      aria-hidden="true"
      className="flex items-center gap-3 border-b border-border bg-surface px-6 py-4"
    >
      <span className="w-1/3">
        <Skeleton />
      </span>
      <span className="w-1/4">
        <Skeleton />
      </span>
    </div>
  );
}
