/**
 * The contract types of the catalog operations, for the mappings in model/ (TS-09).
 */
import type { components } from "@/api/generated/backend";

/** `ShopProductView`: a product of the read-only catalog. */
export type ShopProductContract = components["schemas"]["ShopProductView"];

/** `ShopProductPage`: one page of `listShopProducts`. */
export type ShopProductPageContract = components["schemas"]["ShopProductPage"];
