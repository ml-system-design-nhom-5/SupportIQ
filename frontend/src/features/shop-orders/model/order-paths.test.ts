import { describe, expect, it } from "vitest";

import {
  buildOrderPath,
  ORDER_ROUTE,
  ORDERS_PATH,
  ORDERS_ROUTE,
} from "@/features/shop-orders/model/order-paths";

describe("order paths", () => {
  it("puts My orders and the order route below the shop", () => {
    expect(ORDERS_PATH).toBe("/shop/orders");
    expect(ORDERS_ROUTE).toBe("orders");
    expect(ORDER_ROUTE).toBe("orders/:orderId");
  });

  it("encodes an opaque order ID and the fragment of a ticket (CON-15)", () => {
    expect(buildOrderPath("ORD 1")).toBe("/shop/orders/ORD%201");
    expect(buildOrderPath("ORD-20931", "ticket-TCK-1042")).toBe(
      "/shop/orders/ORD-20931#ticket-TCK-1042",
    );
  });
});
