import { describe, expect, it } from "vitest";

import { orderQueryKeys } from "@/features/shop-orders/api/order-query-keys";

describe("orderQueryKeys", () => {
  it("builds every key under the feature's root key (TS-19)", () => {
    expect(orderQueryKeys.orders()).toEqual(["shop-orders", "orders"]);
    expect(orderQueryKeys.order("ORD-1")).toEqual(["shop-orders", "order", "ORD-1"]);
  });
});
