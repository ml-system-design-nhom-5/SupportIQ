/**
 * The public API of the shop catalog feature: the Products and Product screens (ADR-0013), the
 * shop name, and the catalog paths.
 */
export type { ProductPageProps } from "@/features/shop-catalog/components/product-page";
export { ProductPage } from "@/features/shop-catalog/components/product-page";
export { ProductsPage } from "@/features/shop-catalog/components/products-page";
export {
  buildProductPath,
  PRODUCT_ROUTE,
  PRODUCTS_PATH,
} from "@/features/shop-catalog/model/catalog-paths";
export { buildShopTitle, SHOP_NAME } from "@/features/shop-catalog/model/shop-title";
