/**
 * A ticket of the inbox while the queue loads (UI-24): skeleton lines in the place of an item.
 */
import { Skeleton } from "@/design-system/primitives/skeleton";

/**
 * Render the skeleton of one inbox item.
 *
 * @returns The placeholder lines, hidden from assistive technology.
 */
export function InboxItemSkeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-2 border-b border-border px-4 py-3">
      <Skeleton width="half" />
      <Skeleton width="three-quarters" />
      <Skeleton width="full" />
    </div>
  );
}
