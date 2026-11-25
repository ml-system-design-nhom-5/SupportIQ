import { describe, expect, it } from "vitest";

import { formatMicroUsd, formatMoney } from "@/design-system/format/money";

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

describe("formatMicroUsd", () => {
  it.each([
    [0, "$0.00"],
    [1, "$0.0000010"],
    [420, "$0.00042"],
    [9_999, "$0.010"],
    [10_000, "$0.010"],
    [12_345, "$0.012"],
    [4_200_000, "$4.20"],
    [123_456_789, "$123.46"],
  ])(
    "formats %i micro-USD with at least two decimals and two significant digits as %s",
    (amountMicroUsd, text) => {
      expect(formatMicroUsd(amountMicroUsd)).toBe(text);
    },
  );

  it("formats the largest amount of the contract exactly, without floating-point loss", () => {
    expect(formatMicroUsd(9_007_199_254_740_991)).toBe("$9,007,199,254.74");
  });

  it("rejects a negative amount, which the contract forbids", () => {
    expect(() => formatMicroUsd(-1)).toThrow(RangeError);
  });

  it("rejects an amount that is not an integer", () => {
    expect(() => formatMicroUsd(420.5)).toThrow(RangeError);
  });
});
