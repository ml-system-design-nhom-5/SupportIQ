/**
 * The paths of the catalog screens (shop UI design, Screens): Products at `/shop` and Product at
 * `/shop/products/{product_id}`.
 */
import { rootPathByArea } from "@/features/session";

/** The path of the Products screen: the root of the shop. */
export const PRODUCTS_PATH = rootPathByArea.shop;

const PRODUCTS_SEGMENT = "products";

/** The route of the Product screen, relative to the shop root. */
export const PRODUCT_ROUTE = `${PRODUCTS_SEGMENT}/:productId`;

/**
 * Build the path of a product's page. Product IDs are opaque (CON-15), so they are encoded.
 *
 * @param productId - The `product_id`.
 * @returns For example `/shop/products/PRD-1002`.
 */
export function buildProductPath(productId: string): string {
  return `${PRODUCTS_PATH}/${PRODUCTS_SEGMENT}/${encodeURIComponent(productId)}`;
}
