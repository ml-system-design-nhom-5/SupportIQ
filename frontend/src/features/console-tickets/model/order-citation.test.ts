import { describe, expect, it } from "vitest";

import { toOrderCitationFact } from "@/features/console-tickets/model/order-citation";
import { readContractSchema, readEnumValues } from "@/test/contract-schemas";

/** Every field of `OrderContextField`, in the order of the contract, with a value and its text. */
const fieldCases = [
  ["order_status", "delivered", "Order status", "Delivered"],
  ["placed_at", "2026-10-02T19:30:00Z", "Placed", "2 Oct 2026"],
  ["order_total", { amount_minor: 8900, currency: "USD" }, "Order total", "$89.00"],
  ["shipping_cost", { amount_minor: 500, currency: "USD" }, "Shipping cost", "$5.00"],
  ["shipment_status", "in_transit", "Shipment status", "In transit"],
  ["estimated_delivery_at", "2026-11-07T17:00:00Z", "Estimated delivery", "7 Nov 2026"],
  ["delivered_at", "2026-10-06T12:05:00Z", "Delivered", "6 Oct 2026"],
  ["refund_status", "under_review", "Refund status", "Refund under review"],
  ["refund_amount", { amount_minor: 8900, currency: "USD" }, "Refund amount", "$89.00"],
  ["refund_requested_at", "2026-10-14T09:20:00Z", "Refund requested", "14 Oct 2026"],
] as const;

describe("toOrderCitationFact", () => {
  it("covers every field of OrderContextField", () => {
    expect(fieldCases.map(([field]) => field)).toEqual(
      readEnumValues(readContractSchema("OrderContextField")),
    );
  });

  it.each(fieldCases)("shows the field %s with the value %j", (...fieldCase) => {
    const [field, value, term, shown] = fieldCase;

    expect(toOrderCitationFact(field, value)).toEqual({ term, value: shown });
  });

  it("ignores a field that this version does not know (CON-22)", () => {
    expect(toOrderCitationFact("warehouse_code", "W-1")).toBeUndefined();
  });

  it("shows a status that this version does not know as unknown", () => {
    expect(toOrderCitationFact("refund_status", "partially_paid")).toEqual({
      term: "Refund status",
      value: "Refund status unknown",
    });
  });

  it("stops at an amount without Money", () => {
    expect(() => toOrderCitationFact("order_total", "89.00")).toThrow("no Money value");
  });

  it("stops at a date with Money", () => {
    expect(() => toOrderCitationFact("placed_at", { amount_minor: 1, currency: "USD" })).toThrow(
      "no text value",
    );
  });
});
