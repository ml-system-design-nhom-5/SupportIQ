/**
 * The query keys of the catalog feature (TS-19).
 */

/** The one key factory of the catalog feature. */
export const catalogQueryKeys = {
  all: ["shop-catalog"] as const,
  products: () => [...catalogQueryKeys.all, "products"] as const,
  product: (productId: string) => [...catalogQueryKeys.all, "product", productId] as const,
};
