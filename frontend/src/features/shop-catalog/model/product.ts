/**
 * The view models of the read-only catalog (ADR-0013) and their mappings from the contract (TS-09).
 */
import type { Money } from "@/design-system";
import { requireMembers, toMoney } from "@/features/backend-requests";
import type {
  ShopProductContract,
  ShopProductPageContract,
} from "@/features/shop-catalog/api/contract-types";

/** A product of the catalog. All its fields are Public data. */
export type Product = {
  readonly productId: string;
  readonly name: string;
  /** Plain text; never rendered as HTML (SEC-22). */
  readonly description: string;
  readonly category: string;
  readonly price: Money;
};

/** One page of the catalog (CON-14). */
export type ProductPage = {
  readonly products: readonly Product[];
  /** The cursor of the next page; absent on the last page. */
  readonly nextCursor?: string;
};

/**
 * Map a contract product.
 *
 * @param product - A `ShopProductView`.
 * @returns The view model.
 */
export function toProduct(product: ShopProductContract): Product {
  requireMembers(product, ["product_id", "name", "description", "category", "price"]);
  return {
    productId: product.product_id,
    name: product.name,
    description: product.description,
    category: product.category,
    price: toMoney(product.price),
  };
}

/**
 * Map a page of `listShopProducts`.
 *
 * @param page - A `ShopProductPage`.
 * @returns The products and the cursor of the next page.
 */
export function toProductPage(page: ShopProductPageContract): ProductPage {
  const products = page.items.map(toProduct);
  return page.next_cursor === undefined ? { products } : { products, nextCursor: page.next_cursor };
}
