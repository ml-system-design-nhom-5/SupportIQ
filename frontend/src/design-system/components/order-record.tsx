/**
 * The popover content of one order (console UI design, Order chip, order-single.png): the header
 * that says the data comes from the order records, not from the AI, and the facts of the order.
 */
import { type OrderFactItem, OrderFacts } from "@/design-system/components/order-facts";
import { OrderRecordHeader } from "@/design-system/components/order-record-header";

/** Props of {@link OrderRecord}. */
export type OrderRecordProps = {
  readonly orderId: string;
  readonly facts: readonly OrderFactItem[];
};

/**
 * Render the order.
 *
 * @param props - The order ID and its facts.
 * @returns The header and the padded facts.
 */
export function OrderRecord({ orderId, facts }: OrderRecordProps) {
  return (
    <>
      <OrderRecordHeader title="Order" orderId={orderId} />
      <div className="p-4">
        <OrderFacts facts={facts} />
      </div>
    </>
  );
}
