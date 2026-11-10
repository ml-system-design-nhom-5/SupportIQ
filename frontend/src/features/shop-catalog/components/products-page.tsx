/**
 * The Products screen (`/shop`, shop UI design): the read-only catalog in a grid, with Show more
 * products while there is a next page (CON-14), and every state of the States table.
 */
import { Inbox } from "lucide-react";

import {
  Grid,
  LoadMoreButton,
  PageHeader,
  ProductCard,
  ProductCardSkeleton,
  Stack,
  StateMessage,
  VisuallyHidden,
} from "@/design-system";
import { collectPageItems, FailureBanner, getRequestFailure } from "@/features/backend-requests";
import { AreaLoadFailure } from "@/features/session";
import { useProducts } from "@/features/shop-catalog/api/use-products";
import { buildProductPath } from "@/features/shop-catalog/model/catalog-paths";
import type { Product } from "@/features/shop-catalog/model/product";
import { buildShopTitle } from "@/features/shop-catalog/model/shop-title";

/** The number of placeholder cards while the first page loads. */
const SKELETON_CARD_COUNT = 6;

const skeletonKeys = Array.from(
  { length: SKELETON_CARD_COUNT },
  (_, index) => `skeleton-${String(index)}`,
);

/**
 * Render the Products screen.
 *
 * @returns The screen in the state of its data.
 */
export function ProductsPage() {
  const productsQuery = useProducts();
  const failure = getRequestFailure(productsQuery.error);

  if (productsQuery.data === undefined && failure !== undefined) {
    return (
      <AreaLoadFailure
        area="shop"
        title="Products could not be loaded"
        failure={failure}
        headingLevel={1}
        isRetrying={productsQuery.isFetching}
        onRetry={() => {
          void productsQuery.refetch();
        }}
      />
    );
  }
  if (productsQuery.data === undefined) {
    return (
      <Stack gap="6">
        <title>{buildShopTitle("Products")}</title>
        <PageHeader title="Products" meta="A read-only catalog for the demo" />
        <ProductsLoading />
      </Stack>
    );
  }
  const products = collectPageItems(
    productsQuery.data.pages.map((page) => page.products),
    (product: Product) => product.productId,
  );
  const loadMoreFailure = productsQuery.isFetchNextPageError ? failure : undefined;

  return (
    <Stack gap="6">
      <title>{buildShopTitle("Products")}</title>
      <PageHeader title="Products" meta="A read-only catalog for the demo" />
      {products.length === 0 ? (
        <StateMessage icon={Inbox} headingLevel={2} title="No products to show." />
      ) : (
        <Grid as="ul" label="Products">
          {products.map((product) => (
            <ProductCard
              key={product.productId}
              name={product.name}
              category={product.category}
              price={product.price}
              href={buildProductPath(product.productId)}
            />
          ))}
        </Grid>
      )}
      {loadMoreFailure === undefined ? null : (
        <FailureBanner lead="More products could not be loaded." failure={loadMoreFailure} />
      )}
      {productsQuery.hasNextPage ? (
        <LoadMoreButton
          label="Show more products"
          isLoading={productsQuery.isFetchingNextPage}
          onLoadMore={() => {
            void productsQuery.fetchNextPage();
          }}
        />
      ) : null}
    </Stack>
  );
}

/**
 * Render the loading state: placeholder cards in the grid (UI-24).
 *
 * @returns The busy grid.
 */
function ProductsLoading() {
  return (
    <>
      <p role="status">
        <VisuallyHidden>Loading products…</VisuallyHidden>
      </p>
      <Grid as="ul" label="Products">
        {skeletonKeys.map((key) => (
          <ProductCardSkeleton key={key} />
        ))}
      </Grid>
    </>
  );
}
