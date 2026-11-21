/**
 * The public API of the shop orders feature: the My orders and Order screens (ADR-0013).
 */
export type { OrderPageProps } from "@/features/shop-orders/components/order-page";
export { OrderPage } from "@/features/shop-orders/components/order-page";
export { OrdersPage } from "@/features/shop-orders/components/orders-page";
export {
  buildOrderPath,
  ORDER_ROUTE,
  ORDERS_PATH,
  ORDERS_ROUTE,
} from "@/features/shop-orders/model/order-paths";
