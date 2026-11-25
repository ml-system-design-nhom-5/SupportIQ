/**
 * The loading state of one product card (UI-24).
 */
import { Skeleton } from "@/design-system/primitives/skeleton";

/**
 * Render a placeholder card as a list item of the catalog grid.
 *
 * @returns The list item, hidden from assistive technology; the grid says it is loading.
 */
export function ProductCardSkeleton() {
  return (
    <li
      aria-hidden="true"
      className="flex flex-col gap-3 overflow-hidden rounded-lg border border-border bg-surface pb-4 shadow-sm"
    >
      <Skeleton height="block" />
      <div className="flex flex-col gap-2 px-4">
        <Skeleton width="three-quarters" />
        <Skeleton width="third" />
        <Skeleton width="half" />
      </div>
    </li>
  );
}
