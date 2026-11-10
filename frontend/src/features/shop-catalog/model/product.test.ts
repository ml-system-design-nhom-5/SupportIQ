import { describe, expect, it } from "vitest";

import { toProduct, toProductPage } from "@/features/shop-catalog/model/product";
import { readOperationExample } from "@/test/contract-examples";

describe("toProduct", () => {
  it("maps ShopProductView to a camelCase view model with money in minor units", () => {
    const product = toProduct(readOperationExample("getShopProduct", 200, "found"));

    expect(product).toEqual({
      productId: "PRD-1002",
      name: "Wireless headphones",
      description: "Over-ear headphones with a 30-hour battery.",
      category: "Audio",
      price: { amountMinor: 8900, currency: "USD" },
    });
  });
});

describe("toProductPage", () => {
  it("keeps the cursor of the next page", () => {
    const page = toProductPage(readOperationExample("listShopProducts", 200, "first-page"));

    expect(page.products.map((product) => product.productId)).toEqual(["PRD-1001", "PRD-1003"]);
    expect(page.nextCursor).toBe("eyJwIjoyfQ");
  });

  it("has no cursor on the last page", () => {
    const page = toProductPage(readOperationExample("listShopProducts", 200, "last-page"));

    expect(page).not.toHaveProperty("nextCursor");
    expect(page.products).toHaveLength(2);
  });

  it("maps an empty catalog", () => {
    expect(toProductPage(readOperationExample("listShopProducts", 200, "empty"))).toEqual({
      products: [],
    });
  });
});
