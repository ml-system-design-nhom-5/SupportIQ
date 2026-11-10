/**
 * The Order screen (`/shop/orders/{order_id}`, shop UI design): the order, shipment, and refund
 * statuses, the lines, the total, and Support for this order. "Contact support" moves the focus to
 * the message box. The order loads again when the window regains focus; a failed reload changes
 * nothing on the page (shop UI design, Alternatives considered).
 */
import { MessageSquare, Search } from "lucide-react";
import { type ReactNode, useId } from "react";

import {
  Breadcrumbs,
  Button,
  ButtonLink,
  DateText,
  Identifier,
  OrderSummary,
  PageHeader,
  Skeleton,
  Stack,
  StateMessage,
  VisuallyHidden,
} from "@/design-system";
import {
  categorizeFailure,
  getRequestFailure,
  type RequestFailure,
} from "@/features/backend-requests";
import { AreaLoadFailure } from "@/features/session";
import { buildProductPath, buildShopTitle } from "@/features/shop-catalog";
import { useOrder } from "@/features/shop-orders/api/use-order";
import { buildOrderSummaryStatuses } from "@/features/shop-orders/components/order-presentation";
import type { Order } from "@/features/shop-orders/model/order";
import { ORDERS_PATH } from "@/features/shop-orders/model/order-paths";

/** Props of {@link OrderPage}. */
export type OrderPageProps = {
  /** The `order_id` from the address. */
  readonly orderId: string;
  /**
   * Renders Support for this order, with its message box at the given element ID. The
   * composition root passes the support feature here, so the two features do not import each
   * other (ARCH-18).
   */
  readonly renderSupport: (messageBoxId: string) => ReactNode;
};

/** Props of {@link OrderLoadFailure}. */
type OrderLoadFailureProps = {
  readonly failure: RequestFailure;
  readonly isRetrying: boolean;
  readonly onRetry: () => void;
};

/** Props of {@link OrderContent}. */
type OrderContentProps = {
  readonly order: Order;
  /** The element ID of the message box, which "Contact support" focuses. */
  readonly messageBoxId: string;
  readonly support: ReactNode;
};

/**
 * Render the Order screen.
 *
 * @param props - The order ID and the support section.
 * @returns The screen in the state of its data.
 */
export function OrderPage({ orderId, renderSupport }: OrderPageProps) {
  const orderQuery = useOrder(orderId);
  const messageBoxId = useId();
  const failure = getRequestFailure(orderQuery.error);
  const order = orderQuery.data;

  if (order === undefined && failure !== undefined) {
    return (
      <OrderLoadFailure
        failure={failure}
        isRetrying={orderQuery.isFetching}
        onRetry={() => {
          void orderQuery.refetch();
        }}
      />
    );
  }
  return (
    <Stack gap="6">
      <title>{buildShopTitle(`Order ${orderId}`)}</title>
      <Breadcrumbs
        steps={[
          { label: "My orders", to: ORDERS_PATH },
          { label: orderId, isIdentifier: true },
        ]}
      />
      {order === undefined ? (
        <OrderLoading />
      ) : (
        <OrderContent
          order={order}
          messageBoxId={messageBoxId}
          support={renderSupport(messageBoxId)}
        />
      )}
    </Stack>
  );
}

/**
 * Render the loading state of the order page (shop UI design, order-loading.png).
 *
 * @returns Skeletons in the place of the title and the cards.
 */
function OrderLoading() {
  return (
    <Stack gap="4">
      <p role="status">
        <VisuallyHidden>Loading the order…</VisuallyHidden>
      </p>
      <Skeleton width="half" />
      <Skeleton width="full" height="block" />
      <Skeleton width="full" height="block" />
    </Stack>
  );
}

/**
 * Render the state of an order that could not load: not found for a `404`, which an order of
 * another customer also gets (SEC-17), otherwise the permission-denied or error state.
 *
 * @param props - The failure and the retry handler.
 * @returns The state message.
 */
function OrderLoadFailure({ failure, isRetrying, onRetry }: OrderLoadFailureProps) {
  if (categorizeFailure(failure) === "not_found") {
    return (
      <StateMessage
        icon={Search}
        headingLevel={1}
        title="This order was not found"
        description="It may not exist, or it belongs to another account."
        actions={
          <ButtonLink to={ORDERS_PATH} size="lg">
            Back to My orders
          </ButtonLink>
        }
      />
    );
  }
  return (
    <AreaLoadFailure
      area="shop"
      title="This order could not be loaded"
      failure={failure}
      headingLevel={1}
      isRetrying={isRetrying}
      onRetry={onRetry}
    />
  );
}

/**
 * Render a loaded order with its support section.
 *
 * @param props - The order, the message box ID, and the support section.
 * @returns The header, the order card, and the support section.
 */
function OrderContent({ order, messageBoxId, support }: OrderContentProps) {
  return (
    <>
      <PageHeader
        title={
          <>
            Order <Identifier>{order.orderId}</Identifier>
          </>
        }
        meta={
          <>
            Placed <DateText timestamp={order.placedAt} />
          </>
        }
        action={
          <Button
            size="lg"
            width="full-on-phone"
            leadingIcon={MessageSquare}
            onClick={() => {
              document.getElementById(messageBoxId)?.focus();
            }}
          >
            Contact support
          </Button>
        }
      />
      <OrderSummary
        statuses={buildOrderSummaryStatuses(order)}
        lines={order.lines.map((line) => ({
          // A product appears at most once in an order (decided by the project lead on 2026-11-07).
          key: line.productId,
          productName: line.productName,
          quantity: line.quantity,
          href: buildProductPath(line.productId),
        }))}
        total={order.total}
      />
      {support}
    </>
  );
}
