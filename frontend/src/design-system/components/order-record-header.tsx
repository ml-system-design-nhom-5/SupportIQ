/**
 * The header of a panel of order data (console UI design, Order chip and Order citation marker):
 * the package icon, the title, and "From order records, not AI" (placement rule 9).
 */
import { Package } from "lucide-react";

import { Icon } from "@/design-system/primitives/icon";

/** What the header says about the source of the data. */
const ORDER_RECORDS_NOTE = "From order records, not AI";

/** Props of {@link OrderRecordHeader}. */
export type OrderRecordHeaderProps = {
  /** For example "Order" or "Orders of this customer". */
  readonly title: string;
  /** The order ID after the title, in the monospace family; absent for a list of orders. */
  readonly orderId?: string;
};

/**
 * Render the header.
 *
 * @param props - The title and the order ID.
 * @returns The header row.
 */
export function OrderRecordHeader({ title, orderId }: OrderRecordHeaderProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
      <Icon icon={Package} />
      <p className="font-semibold text-text">
        {title}
        {orderId === undefined ? null : <span className="font-mono"> {orderId}</span>}
      </p>
      <p className="ml-auto text-xs text-text-muted">{ORDER_RECORDS_NOTE}</p>
    </div>
  );
}
