/**
 * The contract types of the order operations, for the mappings in model/ (TS-09).
 */
import type { components } from "@/api/generated/backend";

/** `ShopOrderView`: one of the customer's simulated orders. */
export type ShopOrderContract = components["schemas"]["ShopOrderView"];

/** `ShopOrderPage`: one page of `listShopOrders`. */
export type ShopOrderPageContract = components["schemas"]["ShopOrderPage"];
