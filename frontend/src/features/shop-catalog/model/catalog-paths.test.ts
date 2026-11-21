import { describe, expect, it } from "vitest";

import {
  buildProductPath,
  PRODUCT_ROUTE,
  PRODUCTS_PATH,
} from "@/features/shop-catalog/model/catalog-paths";
import { buildShopTitle, SHOP_NAME } from "@/features/shop-catalog/model/shop-title";

describe("catalog paths", () => {
  it("puts Products at the shop root and the product route below it", () => {
    expect(PRODUCTS_PATH).toBe("/shop");
    expect(PRODUCT_ROUTE).toBe("products/:productId");
  });

  it("encodes an opaque product ID (CON-15)", () => {
    expect(buildProductPath("PRD 1/2")).toBe("/shop/products/PRD%201%2F2");
  });
});

describe("buildShopTitle", () => {
  it("names the page and the shop", () => {
    expect(SHOP_NAME).toBe("Demo Shop");
    expect(buildShopTitle("My orders")).toBe("My orders · Demo Shop");
  });
});
