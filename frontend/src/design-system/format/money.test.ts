import { describe, expect, it } from "vitest";

import { formatMoney } from "@/design-system/format/money";

describe("formatMoney", () => {
  it.each([
    [8900, "USD", "$89.00"],
    [4250, "USD", "$42.50"],
    [5, "USD", "$0.05"],
    [0, "USD", "$0.00"],
    [100, "USD", "$1.00"],
    [123_456_789, "USD", "$1,234,567.89"],
    [890_000, "VND", "₫890,000"],
    [1500, "JPY", "¥1,500"],
  ])("formats %i minor units of %s as %s (CON-16)", (amountMinor, currency, text) => {
    expect(formatMoney({ amountMinor, currency })).toBe(text);
  });

  it("formats the largest amount of the contract exactly, without floating-point loss", () => {
    const text = formatMoney({ amountMinor: 9_007_199_254_740_991, currency: "USD" });

    expect(text).toBe("$90,071,992,547,409.91");
  });

  it("rejects a negative amount, which the contract forbids", () => {
    expect(() => formatMoney({ amountMinor: -1, currency: "USD" })).toThrow(RangeError);
  });

  it("rejects an amount that is not an integer", () => {
    expect(() => formatMoney({ amountMinor: 1.5, currency: "USD" })).toThrow(RangeError);
  });
});
