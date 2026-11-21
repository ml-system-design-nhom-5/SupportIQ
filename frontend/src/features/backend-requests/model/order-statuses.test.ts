import { describe, expect, it } from "vitest";

import {
  toOrderStatus,
  toRefundStatus,
  toShipmentStatus,
} from "@/features/backend-requests/model/order-statuses";

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
