/**
 * Read one product of the catalog (`getShopProduct`).
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { useBackendClient } from "@/api/client";
import { requestData } from "@/features/backend-requests";
import { catalogQueryKeys } from "@/features/shop-catalog/api/catalog-query-keys";
import { type Product, toProduct } from "@/features/shop-catalog/model/product";

/**
 * Read a product.
 *
 * @param productId - The `product_id` from the address.
 * @returns The query of the product; a `404` means that it does not exist.
 */
export function useProduct(productId: string): UseQueryResult<Product> {
  const client = useBackendClient();
  return useQuery({
    queryKey: catalogQueryKeys.product(productId),
    queryFn: ({ signal }) =>
      requestData(
        () =>
          client.GET("/v1/shop/products/{product_id}", {
            params: { path: { product_id: productId } },
            signal,
          }),
        toProduct,
      ),
  });
}
