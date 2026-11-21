/**
 * Read the catalog page by page (`listShopProducts`, CON-14). Each page follows the `next_cursor`
 * of the page before; the first page sends no cursor.
 */
import type { InfiniteData } from "@tanstack/react-query";
import { useInfiniteQuery, type UseInfiniteQueryResult } from "@tanstack/react-query";

import { useBackendClient } from "@/api/client";
import { requestData } from "@/features/backend-requests";
import { catalogQueryKeys } from "@/features/shop-catalog/api/catalog-query-keys";
import { type ProductPage, toProductPage } from "@/features/shop-catalog/model/product";

/**
 * Read the pages of the catalog.
 *
 * @returns The infinite query; `fetchNextPage` loads the next page while there is one.
 */
export function useProducts(): UseInfiniteQueryResult<
  InfiniteData<ProductPage, string | undefined>
> {
  const client = useBackendClient();
  return useInfiniteQuery({
    queryKey: catalogQueryKeys.products(),
    initialPageParam: undefined,
    queryFn: ({ pageParam, signal }: { pageParam: string | undefined; signal: AbortSignal }) =>
      requestData(
        () =>
          client.GET("/v1/shop/products", {
            params: { query: pageParam === undefined ? {} : { cursor: pageParam } },
            signal,
          }),
        toProductPage,
      ),
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  });
}
