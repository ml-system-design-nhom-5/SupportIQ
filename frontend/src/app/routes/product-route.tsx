/**
 * The route element of the Product screen: it reads the product ID from the address.
 */
import { useRouteParam } from "@/app/routes/route-params";
import { ProductPage } from "@/features/shop-catalog";

/**
 * Render the Product screen of the product in the address.
 *
 * @returns The screen.
 */
export function ProductRoute() {
  return <ProductPage productId={useRouteParam("productId")} />;
}
