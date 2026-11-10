/**
 * The "Show more" button of a paginated list (CON-14, shop UI design, Loading more). The items
 * already shown stay while the next page loads.
 */
import { ChevronDown } from "lucide-react";

import { Button, type ButtonSize } from "@/design-system/primitives/button";

/** Props of {@link LoadMoreButton}. */
export type LoadMoreButtonProps = {
  /** A verb phrase, for example "Show more products". */
  readonly label: string;
  readonly isLoading: boolean;
  readonly size?: ButtonSize;
  readonly onLoadMore: () => void;
};

/**
 * Render the button. It ignores activation while the next page loads, so one click loads one
 * page, and it keeps the focus.
 *
 * @param props - The label, the loading state, the size, and the handler.
 * @returns The centered button.
 */
export function LoadMoreButton({ label, isLoading, size = "lg", onLoadMore }: LoadMoreButtonProps) {
  // TODO(#7): a list removes this button after its last page, and the focus falls to the page
  // (UI-30).
  return (
    <div className="flex justify-center">
      <Button leadingIcon={ChevronDown} size={size} isPending={isLoading} onClick={onLoadMore}>
        {isLoading ? "Loading…" : label}
      </Button>
    </div>
  );
}
