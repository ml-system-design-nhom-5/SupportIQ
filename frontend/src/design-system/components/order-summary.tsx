/**
 * The order card of the Order screen (shop UI design, Order): the order, shipment, and refund
 * statuses with their dates, the lines with links to their products, and the total. The contract
 * has no price per line, so the card shows none.
 */
import type { ReactNode } from "react";

import { MoneyText } from "@/design-system/components/money-text";
import { ProductImage } from "@/design-system/components/product-image";
import { StatusBadge } from "@/design-system/components/status-badge";
import type { StatusPresentation } from "@/design-system/components/status-presentations";
import type { Money } from "@/design-system/format/money";
import { formatCount } from "@/design-system/format/number";
import { TextLink } from "@/design-system/primitives/text-link";

/** One status cell: "Order", "Shipment", or "Refund", its badge, and a date line. */
export type OrderSummaryStatus = {
  readonly label: string;
  readonly presentation: StatusPresentation;
  /** For example "Placed 2 Oct 2026"; absent when there is no date to show. */
  readonly detail?: ReactNode;
};

/** One line of the order. */
export type OrderSummaryLine = {
  /** A stable key for the line (TS-24). */
  readonly key: string;
  readonly productName: string;
  readonly quantity: number;
  /** The path of the product page. */
  readonly href: string;
};

/** Props of {@link OrderSummary}. */
export type OrderSummaryProps = {
  readonly statuses: readonly OrderSummaryStatus[];
  readonly lines: readonly OrderSummaryLine[];
  readonly total: Money;
};

/**
 * Render the order card.
 *
 * @param props - The statuses, the lines, and the total.
 * @returns The card.
 */
export function OrderSummary({ statuses, lines, total }: OrderSummaryProps) {
  return (
    <section
      aria-label="Order details"
      className="flex flex-col rounded-lg border border-border bg-surface shadow-sm"
    >
      <dl className="grid grid-cols-1 gap-3 px-4 py-4 sm:grid-cols-3 sm:gap-4 sm:px-6">
        {statuses.map((status) => (
          <div
            key={status.label}
            className="flex flex-wrap items-center gap-2 sm:flex-col sm:items-start sm:gap-1"
          >
            <dt className="min-w-16 text-sm text-text-muted">{status.label}</dt>
            <dd>
              <StatusBadge presentation={status.presentation} />
            </dd>
            {status.detail === undefined ? null : (
              <dd className="w-full text-sm text-text-muted sm:w-auto">{status.detail}</dd>
            )}
          </div>
        ))}
      </dl>
      <div className="flex flex-col gap-3 border-t border-border px-4 py-4 sm:px-6">
        <ul aria-label="Order lines" className="flex flex-col gap-3">
          {lines.map((line) => (
            <li key={line.key} className="flex items-center gap-4">
              <ProductImage size="thumbnail" />
              <span className="flex min-w-0 flex-col">
                <TextLink to={line.href} emphasis="strong">
                  {line.productName}
                </TextLink>
                <span className="text-sm text-text-muted">
                  Quantity {formatCount(line.quantity)}
                </span>
              </span>
            </li>
          ))}
        </ul>
        <p className="flex justify-end gap-4 border-t border-border pt-3 text-lg font-semibold text-text">
          <span>Total</span>
          <MoneyText money={total} />
        </p>
      </div>
    </section>
  );
}
