/**
 * The My orders screen (`/shop/orders`, shop UI design): the customer's orders, newest first, with
 * Show more orders while there is a next page (CON-14), and every state of the States table.
 */
import { Inbox } from "lucide-react";

import {
  LoadMoreButton,
  OrderRow,
  PageHeader,
  RowList,
  Skeleton,
  Stack,
  StateMessage,
  VisuallyHidden,
} from "@/design-system";
import { collectPageItems, FailureBanner, getRequestFailure } from "@/features/backend-requests";
import { AreaLoadFailure } from "@/features/session";
import { buildShopTitle } from "@/features/shop-catalog";
import { useOrders } from "@/features/shop-orders/api/use-orders";
import { buildOrderRowStatuses } from "@/features/shop-orders/components/order-presentation";
import { type Order, summarizeOrderLines } from "@/features/shop-orders/model/order";
import { buildOrderPath } from "@/features/shop-orders/model/order-paths";

/**
 * Render the My orders screen.
 *
 * @returns The screen in the state of its data.
 */
export function OrdersPage() {
  const ordersQuery = useOrders();
  const failure = getRequestFailure(ordersQuery.error);

  if (ordersQuery.data === undefined && failure !== undefined) {
    return (
      <AreaLoadFailure
        area="shop"
        title="Your orders could not be loaded"
        failure={failure}
        headingLevel={1}
        isRetrying={ordersQuery.isFetching}
        onRetry={() => {
          void ordersQuery.refetch();
        }}
      />
    );
  }
  const orders =
    ordersQuery.data === undefined
      ? undefined
      : collectPageItems(
          ordersQuery.data.pages.map((page) => page.orders),
          (order: Order) => order.orderId,
        );
  const loadMoreFailure = ordersQuery.isFetchNextPageError ? failure : undefined;

  return (
    <Stack gap="6">
      <title>{buildShopTitle("My orders")}</title>
      <PageHeader title="My orders" />
      {orders === undefined ? <OrdersLoading /> : <OrderList orders={orders} />}
      {loadMoreFailure === undefined ? null : (
        <FailureBanner lead="More orders could not be loaded." failure={loadMoreFailure} />
      )}
      {ordersQuery.hasNextPage ? (
        <LoadMoreButton
          label="Show more orders"
          isLoading={ordersQuery.isFetchingNextPage}
          onLoadMore={() => {
            void ordersQuery.fetchNextPage();
          }}
        />
      ) : null}
    </Stack>
  );
}

/**
 * Render the loading state of the list (UI-24).
 *
 * @returns Skeleton rows.
 */
function OrdersLoading() {
  return (
    <Stack gap="3">
      <p role="status">
        <VisuallyHidden>Loading your orders…</VisuallyHidden>
      </p>
      <Skeleton width="full" height="block" />
      <Skeleton width="full" height="block" />
    </Stack>
  );
}

/**
 * Render the orders of the loaded pages.
 *
 * @param props - The orders.
 * @returns The list, or the empty state.
 */
function OrderList({ orders }: { readonly orders: readonly Order[] }) {
  if (orders.length === 0) {
    return <StateMessage icon={Inbox} headingLevel={2} title="You have no orders yet." />;
  }
  return (
    <RowList label="Your orders">
      {orders.map((order) => (
        <OrderRow
          key={order.orderId}
          orderId={order.orderId}
          placedAt={order.placedAt}
          productSummary={summarizeOrderLines(order.lines)}
          statuses={buildOrderRowStatuses(order)}
          total={order.total}
          href={buildOrderPath(order.orderId)}
        />
      ))}
    </RowList>
  );
}
