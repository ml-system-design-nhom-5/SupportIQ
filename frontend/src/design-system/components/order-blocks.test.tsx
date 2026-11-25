import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OrderRow } from "@/design-system/components/order-row";
import { OrderSummary } from "@/design-system/components/order-summary";
import { RowList } from "@/design-system/components/row-list";
import {
  presentationByOrderStatus,
  presentationByRefundStatus,
  presentationByShipmentStatus,
} from "@/design-system/components/status-presentations";
import { renderUi } from "@/test/render-app";

describe("OrderRow", () => {
  it("links the whole row to the order and shows its date, products, statuses, and total", () => {
    renderUi(
      <RowList label="Your orders">
        <OrderRow
          orderId="ORD-20931"
          placedAt="2026-10-02T19:30:00Z"
          productSummary="Wireless headphones"
          total={{ amountMinor: 8900, currency: "USD" }}
          href="/shop/orders/ORD-20931"
          statuses={[
            { label: "Order", presentation: presentationByOrderStatus.delivered },
            { label: "Shipment", presentation: presentationByShipmentStatus.delivered },
            { presentation: presentationByRefundStatus.under_review },
          ]}
        />
      </RowList>,
    );

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/shop/orders/ORD-20931");
    expect(link).toHaveTextContent("Order ORD-20931");
    expect(link).toHaveTextContent("Placed 2 Oct 2026");
    expect(link).toHaveTextContent("Wireless headphones");
    expect(link).toHaveTextContent("OrderDelivered");
    expect(link).toHaveTextContent("Refund under review");
    expect(link).toHaveTextContent("$89.00");
  });
});

describe("OrderSummary", () => {
  it("lists each status with its date, each line with its product link, and the total", () => {
    renderUi(
      <OrderSummary
        statuses={[
          {
            label: "Order",
            presentation: presentationByOrderStatus.shipped,
            detail: "Placed 28 Oct 2026",
          },
          { label: "Shipment", presentation: presentationByShipmentStatus.in_transit },
          {
            label: "Refund",
            presentation: presentationByRefundStatus.none,
            detail: "Not requested",
          },
        ]}
        lines={[
          { key: "0", productName: "Desk lamp", quantity: 1, href: "/shop/products/PRD-1001" },
          { key: "1", productName: "Notebook set", quantity: 2, href: "/shop/products/PRD-1003" },
        ]}
        total={{ amountMinor: 4250, currency: "USD" }}
      />,
    );

    const details = screen.getByRole("region", { name: "Order details" });
    expect(
      within(details)
        .getAllByRole("term")
        .map((term) => term.textContent),
    ).toEqual(["Order", "Shipment", "Refund"]);
    expect(within(details).getByText("Placed 28 Oct 2026")).toBeVisible();
    expect(within(details).getByText("Not requested")).toBeVisible();
    const lines = within(details).getByRole("list", { name: "Order lines" });
    expect(within(lines).getByRole("link", { name: "Notebook set" })).toHaveAttribute(
      "href",
      "/shop/products/PRD-1003",
    );
    expect(within(lines).getByText("Quantity 2")).toBeVisible();
    expect(within(details).getByText("$42.50")).toBeVisible();
  });
});
