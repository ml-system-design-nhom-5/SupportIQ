import { describe, expect, it } from "vitest";

import type {
  ConsoleOrderContract,
  ConsoleOtherOrderContract,
} from "@/features/console-tickets/api/contract-types";
import {
  buildOrderFacts,
  buildTicketOrderFacts,
  summarizeOrder,
  toOrder,
  toTicketOrder,
} from "@/features/console-tickets/model/order";
import { readOperationExample, withoutMembers } from "@/test/contract-examples";

const workspace = readOperationExample("getConsoleTicket", 200, "draft-ready");

/**
 * Read the order of the draft-ready example.
 *
 * @returns The ticket's order.
 */
function readTicketOrder(): ConsoleOrderContract {
  if (workspace.order === undefined) {
    throw new Error("The draft-ready example has no order.");
  }
  return workspace.order;
}

/**
 * Read the other order of the draft-ready example.
 *
 * @returns The customer's other order.
 */
function readOtherOrder(): ConsoleOtherOrderContract {
  const order = workspace.other_orders?.[0];
  if (order === undefined) {
    throw new Error("The draft-ready example has no other order.");
  }
  return order;
}

describe("toTicketOrder", () => {
  it("maps the ticket's order with its shipment, refund, and shipping address", () => {
    expect(toTicketOrder(readTicketOrder())).toEqual({
      orderId: "ORD-20931",
      status: "delivered",
      placedAt: "2026-10-02T19:30:00Z",
      total: { amountMinor: 8900, currency: "USD" },
      lines: [{ productName: "Wireless headphones", quantity: 1 }],
      shipmentStatus: "delivered",
      refundStatus: "under_review",
      shippingCost: { amountMinor: 0, currency: "USD" },
      shippingAddress: "12 Sample Street, Sample City",
      deliveredAt: "2026-10-06T12:05:00Z",
      refundRequestedAt: "2026-10-14T09:20:00Z",
    });
  });

  it("maps an order without a shipment and without a refund", () => {
    const mapped = toTicketOrder(withoutMembers(readTicketOrder(), ["shipment", "refund"]));

    expect(mapped).not.toHaveProperty("shipmentStatus");
    expect(mapped).not.toHaveProperty("refundStatus");
    expect(mapped).not.toHaveProperty("refundRequestedAt");
  });
});

describe("toOrder", () => {
  it("maps another order of the customer, which has no shipping address (SEC-17)", () => {
    expect(toOrder(readOtherOrder())).toEqual({
      orderId: "ORD-20990",
      status: "shipped",
      placedAt: "2026-10-28T15:10:00Z",
      total: { amountMinor: 3450, currency: "USD" },
      lines: [{ productName: "Desk lamp", quantity: 1 }],
      shipmentStatus: "in_transit",
    });
  });
});

describe("summarizeOrder", () => {
  it.each([
    ["the ticket's order", toTicketOrder(readTicketOrder()), "Delivered · Refund under review"],
    ["an order without a refund", toOrder(readOtherOrder()), "Shipped · No refund"],
  ])("summarizes %s", (_case, order, summary) => {
    expect(summarizeOrder(order)).toBe(summary);
  });
});

describe("buildTicketOrderFacts", () => {
  it("lists the facts of the ticket's order, with the shipping address", () => {
    expect(buildTicketOrderFacts(toTicketOrder(readTicketOrder()))).toEqual([
      { term: "Order", value: "Delivered", detail: "Placed 2 Oct 2026" },
      { term: "Shipment", value: "Delivered", detail: "Delivered 6 Oct 2026" },
      { term: "Refund", value: "Refund under review", detail: "Requested 14 Oct 2026" },
      { term: "Total", value: "$89.00", detail: "1 item" },
      { term: "Items", value: "Wireless headphones × 1" },
      { term: "Shipping", value: "$0.00" },
      { term: "Ship to", value: "12 Sample Street, Sample City" },
    ]);
  });
});

describe("buildOrderFacts", () => {
  it("lists the facts of another order, without an address", () => {
    expect(buildOrderFacts(toOrder(readOtherOrder()))).toEqual([
      { term: "Order", value: "Shipped", detail: "Placed 28 Oct 2026" },
      { term: "Shipment", value: "In transit" },
      { term: "Refund", value: "No refund" },
      { term: "Total", value: "$34.50", detail: "1 item" },
      { term: "Items", value: "Desk lamp × 1" },
    ]);
  });

  it("says when an order has no shipment, and counts several items", () => {
    const facts = buildOrderFacts({
      ...toOrder(withoutMembers(readOtherOrder(), ["shipment_status"])),
      lines: [
        { productName: "Desk lamp", quantity: 2 },
        { productName: "Notebook set", quantity: 1 },
      ],
    });

    expect(facts).toContainEqual({ term: "Shipment", value: "No shipment" });
    expect(facts).toContainEqual({ term: "Total", value: "$34.50", detail: "3 items" });
    expect(facts).toContainEqual({ term: "Items", value: "Desk lamp × 2, Notebook set × 1" });
  });

  it("shows the expected delivery of a shipment that is on its way", () => {
    const facts = buildOrderFacts({
      ...toOrder(readOtherOrder()),
      estimatedDeliveryAt: "2026-11-07T17:00:00Z",
    });

    expect(facts).toContainEqual({
      term: "Shipment",
      value: "In transit",
      detail: "Due 7 Nov 2026",
    });
  });
});
