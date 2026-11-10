/**
 * The Product screen (`/shop/products/{product_id}`, shop UI design): the product's details under
 * the path back to Products, and every state of the States table.
 */
import { Search } from "lucide-react";

import {
  Breadcrumbs,
  ButtonLink,
  ProductDetails,
  Skeleton,
  Stack,
  StateMessage,
  VisuallyHidden,
} from "@/design-system";
import {
  categorizeFailure,
  getRequestFailure,
  type RequestFailure,
} from "@/features/backend-requests";
import { AreaLoadFailure } from "@/features/session";
import { useProduct } from "@/features/shop-catalog/api/use-product";
import { PRODUCTS_PATH } from "@/features/shop-catalog/model/catalog-paths";
import { buildShopTitle } from "@/features/shop-catalog/model/shop-title";

/** Props of {@link ProductPage}. */
export type ProductPageProps = {
  /** The `product_id` from the address. */
  readonly productId: string;
};

/** Props of {@link ProductLoadFailure}. */
type ProductLoadFailureProps = {
  readonly failure: RequestFailure;
  readonly isRetrying: boolean;
  readonly onRetry: () => void;
};

/**
 * Render the Product screen.
 *
 * @param props - The product ID.
 * @returns The screen in the state of its data.
 */
export function ProductPage({ productId }: ProductPageProps) {
  const productQuery = useProduct(productId);
  const failure = getRequestFailure(productQuery.error);
  const product = productQuery.data;

  if (product === undefined && failure !== undefined) {
    return (
      <ProductLoadFailure
        failure={failure}
        isRetrying={productQuery.isFetching}
        onRetry={() => {
          void productQuery.refetch();
        }}
      />
    );
  }
  const productName = product?.name ?? "Product";
  return (
    <Stack gap="6">
      <title>{buildShopTitle(productName)}</title>
      <Breadcrumbs steps={[{ label: "Products", to: PRODUCTS_PATH }, { label: productName }]} />
      {product === undefined ? (
        <ProductLoading />
      ) : (
        <ProductDetails
          name={product.name}
          category={product.category}
          price={product.price}
          description={product.description}
        />
      )}
    </Stack>
  );
}

/**
 * Render the loading state of the product page.
 *
 * @returns Skeletons in the place of the details.
 */
function ProductLoading() {
  return (
    <Stack gap="3">
      <p role="status">
        <VisuallyHidden>Loading the product…</VisuallyHidden>
      </p>
      <Skeleton height="block" />
      <Skeleton width="half" />
      <Skeleton width="third" />
    </Stack>
  );
}

/**
 * Render the state of a product that could not load: not found for a `404`, otherwise the
 * permission-denied or error state of the shop.
 *
 * @param props - The failure and the retry handler.
 * @returns The state message.
 */
function ProductLoadFailure({ failure, isRetrying, onRetry }: ProductLoadFailureProps) {
  if (categorizeFailure(failure) === "not_found") {
    return (
      <StateMessage
        icon={Search}
        headingLevel={1}
        title="This product was not found"
        description="Check the link, or go back to the catalog."
        actions={
          <ButtonLink to={PRODUCTS_PATH} size="lg">
            Back to Products
          </ButtonLink>
        }
      />
    );
  }
  return (
    <AreaLoadFailure
      area="shop"
      title="This product could not be loaded"
      failure={failure}
      headingLevel={1}
      isRetrying={isRetrying}
      onRetry={onRetry}
    />
  );
}
