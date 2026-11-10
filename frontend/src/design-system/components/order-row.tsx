/**
 * One order in My orders (shop UI design, My orders): the order ID, the date it was placed, the
 * product names, the statuses, and the total. The whole row opens the order page.
 */
import { DateText } from "@/design-system/components/date-text";
import { MoneyText } from "@/design-system/components/money-text";
import { RowListItem } from "@/design-system/components/row-list-item";
import { StatusBadge } from "@/design-system/components/status-badge";
import type { StatusPresentation } from "@/design-system/components/status-presentations";
import type { Money } from "@/design-system/format/money";

/** One status of the row, with an optional label before its badge, such as "Order". */
export type OrderRowStatus = {
  readonly label?: string;
  readonly presentation: StatusPresentation;
};

/** Props of {@link OrderRow}. */
export type OrderRowProps = {
  readonly orderId: string;
  /** When the customer placed the order, as an RFC 3339 timestamp. */
  readonly placedAt: string;
  /** The product names, for example "Desk lamp, Notebook set × 2". */
  readonly productSummary: string;
  readonly statuses: readonly OrderRowStatus[];
  readonly total: Money;
  /** The path of the order page. */
  readonly href: string;
};

/**
 * Render an order row inside a {@link RowList}.
 *
 * @param props - The order's ID, date, products, statuses, total, and path.
 * @returns The list item.
 */
export function OrderRow({
  orderId,
  placedAt,
  productSummary,
  statuses,
  total,
  href,
}: OrderRowProps) {
  return (
    <RowListItem
      to={href}
      trailing={
        <span className="text-base font-medium text-text">
          <MoneyText money={total} />
        </span>
      }
    >
      <span className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="min-w-0 text-base font-semibold">
          Order <span className="font-mono text-xs">{orderId}</span>
        </span>
        <span className="text-xs text-text-muted">
          Placed <DateText timestamp={placedAt} />
        </span>
      </span>
      <span className="truncate text-base text-text-muted">{productSummary}</span>
      <span className="flex flex-wrap items-center gap-x-2 gap-y-2 text-xs text-text-muted">
        {statuses.map((status) => (
          <span key={status.label ?? status.presentation.label} className="flex items-center gap-1">
            {status.label}
            <StatusBadge presentation={status.presentation} />
          </span>
        ))}
      </span>
    </RowListItem>
  );
}
