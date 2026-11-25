/**
 * The order chip of the ticket header (console UI design, Order chip): the order ID and the
 * statuses of the order stay visible without a click (placement rule 8). It opens a popover with
 * the rest. When the customer has other orders, the chip adds "+2 orders" and the popover becomes
 * a list with a preview. Order data comes from the order records, not from the AI, so the chip
 * never carries the `ai` marker (placement rule 9).
 */
import { ChevronDown, Package } from "lucide-react";
import type { ReactNode } from "react";

import { formatCount } from "@/design-system/format/number";
import { cn } from "@/design-system/primitives/class-names";
import type { DialogReturnFocus } from "@/design-system/primitives/dialog-return-focus";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";
import { Popover } from "@/design-system/primitives/popover";

/** Props of {@link OrderChip}. */
export type OrderChipProps = {
  readonly orderId: string;
  /** The statuses of the order, for example "Delivered · Refund under review". */
  readonly summary: string;
  /** How many other orders the customer has; 0 when none. */
  readonly otherOrderCount: number;
  readonly isOpen: boolean;
  readonly onOpenChange: (isOpen: boolean) => void;
  /** Where the focus goes when an order citation marker opened the popover; the chip otherwise. */
  readonly returnFocus?: DialogReturnFocus;
  /** The content of the popover. */
  readonly children: ReactNode;
};

/**
 * Render the chip and its popover.
 *
 * @param props - The order, the count of other orders, the popover state, where the focus returns,
 *   and the content of the popover.
 * @returns The chip; the popover opens in a portal.
 */
export function OrderChip({
  orderId,
  summary,
  otherOrderCount,
  isOpen,
  onOpenChange,
  returnFocus,
  children,
}: OrderChipProps) {
  const hasOtherOrders = otherOrderCount > 0;
  const otherOrdersLabel = `+${formatCount(otherOrderCount)} ${otherOrderCount === 1 ? "order" : "orders"}`;
  return (
    <Popover
      label={hasOtherOrders ? "Orders of this customer" : `Order ${orderId}`}
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      width={hasOtherOrders ? "wide" : "narrow"}
      {...(returnFocus === undefined ? {} : { returnFocus })}
      trigger={
        <button
          type="button"
          className={cn(
            "flex h-8 min-w-0 items-center gap-2 rounded-md border border-border-strong bg-surface px-3 text-sm text-text hover:bg-background aria-expanded:bg-background",
            FOCUS_RING_CLASSES,
          )}
        >
          <Icon icon={Package} />
          {/* The spaces between the parts keep the accessible name readable (WCAG 2.5.3). */}
          <span className="shrink-0 font-mono text-xs whitespace-nowrap">{orderId}</span>{" "}
          <span className="truncate text-xs">{summary}</span>{" "}
          {hasOtherOrders ? (
            <span className="rounded-sm bg-background px-1 text-xs whitespace-nowrap text-text-muted">
              {otherOrdersLabel}
            </span>
          ) : null}
          <Icon icon={ChevronDown} />
        </button>
      }
    >
      {children}
    </Popover>
  );
}
