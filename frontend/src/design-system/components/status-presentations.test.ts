import { describe, expect, it } from "vitest";

import {
  presentationByAccountStatus,
  presentationByInternalRole,
  presentationByOrderStatus,
  presentationByRefundStatus,
  presentationByShipmentStatus,
  presentationByShopTicketStatus,
} from "@/design-system/components/status-presentations";

describe("shop status presentations (UI-12, shop UI design)", () => {
  it.each([
    ["placed", "neutral", "Placed"],
    ["processing", "info", "Processing"],
    ["shipped", "info", "Shipped"],
    ["delivered", "success", "Delivered"],
    ["cancelled", "neutral", "Cancelled"],
    ["unknown", "neutral", "Status unknown"],
  ] as const)("presents the order status %s in the %s tone as %s", (status, tone, label) => {
    expect(presentationByOrderStatus[status]).toMatchObject({ tone, label });
  });

  it.each([
    ["not_shipped", "neutral", "Not shipped"],
    ["in_transit", "info", "In transit"],
    ["delivered", "success", "Delivered"],
    ["delayed", "warning", "Delayed"],
    ["lost", "danger", "Lost"],
    ["unknown", "neutral", "Status unknown"],
  ] as const)("presents the shipment status %s in the %s tone as %s", (status, tone, label) => {
    expect(presentationByShipmentStatus[status]).toMatchObject({ tone, label });
  });

  it.each([
    ["requested", "info", "Refund requested"],
    ["under_review", "info", "Refund under review"],
    ["approved", "success", "Refund approved"],
    ["rejected", "danger", "Refund rejected"],
    ["paid", "success", "Refund paid"],
    ["none", "neutral", "No refund"],
    ["unknown", "neutral", "Refund status unknown"],
  ] as const)("presents the refund status %s in the %s tone as %s", (status, tone, label) => {
    expect(presentationByRefundStatus[status]).toMatchObject({ tone, label });
  });
});

describe("ticket and account status presentations (UI-12, shop UI and admin UI designs)", () => {
  it.each([
    ["received", "info", "Received"],
    ["replied", "success", "Replied"],
  ] as const)("presents the ticket status %s in the %s tone as %s", (status, tone, label) => {
    expect(presentationByShopTicketStatus[status]).toMatchObject({ tone, label });
  });

  it.each([
    ["staff", "neutral", "Staff"],
    ["manager", "info", "Manager"],
    ["admin", "neutral", "Admin"],
    ["unknown", "neutral", "Unknown role"],
  ] as const)("presents the role %s in the %s tone as %s", (role, tone, label) => {
    expect(presentationByInternalRole[role]).toMatchObject({ tone, label });
  });

  it.each([
    ["active", "success", "Active"],
    ["deactivated", "neutral", "Deactivated"],
  ] as const)("presents the account status %s in the %s tone as %s", (status, tone, label) => {
    expect(presentationByAccountStatus[status]).toMatchObject({ tone, label });
  });
});
