import { describe, expect, it } from "vitest";

import {
  summarizeOrderLines,
  toOrder,
  toOrderPage,
  toOrderStatus,
  toRefundStatus,
  toShipmentStatus,
} from "@/features/shop-orders/model/order";
import { readOperationExample } from "@/test/contract-examples";

describe("toOrder", () => {
  it("maps an order with a refund, keeping money in minor units", () => {
    const order = toOrder(readOperationExample("getShopOrder", 200, "refund-under-review"));

    expect(order).toEqual({
      orderId: "ORD-20931",
      status: "delivered",
      placedAt: "2026-10-02T19:30:00Z",
      total: { amountMinor: 8900, currency: "USD" },
      lines: [{ productId: "PRD-1002", productName: "Wireless headphones", quantity: 1 }],
      shipment: { status: "delivered", deliveredAt: "2026-10-06T12:05:00Z" },
      refund: {
        status: "under_review",
        requestedAt: "2026-10-14T09:20:00Z",
      },
    });
  });

  it("maps an order without a refund and with a delivery estimate", () => {
    const order = toOrder(readOperationExample("getShopOrder", 200, "in-transit"));

    expect(order).not.toHaveProperty("refund");
    expect(order.shipment).toEqual({
      status: "in_transit",
      estimatedDeliveryAt: "2026-11-07T17:00:00Z",
    });
    expect(order.lines).toHaveLength(2);
  });

  it("maps a shipment without any date", () => {
    const page = toOrderPage(readOperationExample("listShopOrders", 200, "last-page"));

    expect(page.orders[1]?.shipment).toEqual({ status: "not_shipped" });
  });
});

describe("toOrderPage", () => {
  it("keeps the cursor of the next page", () => {
    const page = toOrderPage(readOperationExample("listShopOrders", 200, "first-page"));

    expect(page.orders.map((order) => order.orderId)).toEqual(["ORD-20990", "ORD-20955"]);
    expect(page.nextCursor).toBe("eyJvIjoyfQ");
  });

  it("has no cursor on the last page and maps an empty list", () => {
    expect(
      toOrderPage(readOperationExample("listShopOrders", 200, "last-page")),
    ).not.toHaveProperty("nextCursor");
    expect(toOrderPage(readOperationExample("listShopOrders", 200, "empty"))).toEqual({
      orders: [],
    });
  });
});

describe("status mappings (CON-22, TS-15)", () => {
  it.each(["placed", "processing", "shipped", "delivered", "cancelled"])(
    "keeps the order status %s",
    (status) => {
      expect(toOrderStatus(status)).toBe(status);
    },
  );

  it.each(["not_shipped", "in_transit", "delivered", "delayed", "lost"])(
    "keeps the shipment status %s",
    (status) => {
      expect(toShipmentStatus(status)).toBe(status);
    },
  );

  it.each(["requested", "under_review", "approved", "rejected", "paid"])(
    "keeps the refund status %s",
    (status) => {
      expect(toRefundStatus(status)).toBe(status);
    },
  );

  it.each([
    ["order", toOrderStatus],
    ["shipment", toShipmentStatus],
    ["refund", toRefundStatus],
  ] as const)("maps an unknown %s status to unknown", (_kind, toStatus) => {
    expect(toStatus("returned_to_sender")).toBe("unknown");
    expect(toStatus("")).toBe("unknown");
  });
});

describe("summarizeOrderLines", () => {
  it("names one product without its quantity", () => {
    expect(
      summarizeOrderLines([{ productId: "PRD-1", productName: "Desk lamp", quantity: 1 }]),
    ).toBe("Desk lamp");
  });

  it("adds the quantity of a line with more than one unit, like the mockup", () => {
    expect(
      summarizeOrderLines([
        { productId: "PRD-1", productName: "Desk lamp", quantity: 1 },
        { productId: "PRD-3", productName: "Notebook set", quantity: 2 },
      ]),
    ).toBe("Desk lamp, Notebook set × 2");
  });

  it("formats a large quantity with the shared formatter", () => {
    expect(summarizeOrderLines([{ productId: "PRD-1", productName: "Bolt", quantity: 1200 }])).toBe(
      "Bolt × 1,200",
    );
  });
});
