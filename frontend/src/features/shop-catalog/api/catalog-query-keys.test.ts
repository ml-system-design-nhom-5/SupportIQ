import { describe, expect, it } from "vitest";

import { catalogQueryKeys } from "@/features/shop-catalog/api/catalog-query-keys";

describe("catalogQueryKeys", () => {
  it("builds every key under the feature's root key (TS-19)", () => {
    expect(catalogQueryKeys.products()).toEqual(["shop-catalog", "products"]);
    expect(catalogQueryKeys.product("PRD-1002")).toEqual(["shop-catalog", "product", "PRD-1002"]);
  });
});
