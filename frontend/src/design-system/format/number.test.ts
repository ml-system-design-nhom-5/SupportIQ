import { describe, expect, it } from "vitest";

import { formatCount, formatPercent, formatShareOneDecimal } from "@/design-system/format/number";

describe("formatCount", () => {
  it.each([
    [0, "0"],
    [2000, "2,000"],
    [1_234_567, "1,234,567"],
  ])("formats %i as %s", (count, text) => {
    expect(formatCount(count)).toBe(text);
  });
});

describe("formatPercent", () => {
  it.each([
    [0, "0%"],
    [0.07, "7%"],
    [0.885, "89%"],
    [1, "100%"],
  ])("formats the share %d as %s", (share, text) => {
    expect(formatPercent(share)).toBe(text);
  });
});

describe("formatShareOneDecimal", () => {
  it.each([
    [0, "0%"],
    [0.25, "25%"],
    [0.018, "1.8%"],
    [0.462, "46.2%"],
    [0.4615, "46.2%"],
    [0.9996, "100%"],
    [1, "100%"],
  ])("formats the share %d with at most one decimal as %s", (share, text) => {
    expect(formatShareOneDecimal(share)).toBe(text);
  });
});
