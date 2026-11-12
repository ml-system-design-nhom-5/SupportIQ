import { describe, expect, it } from "vitest";

import { formatCount, formatPercent } from "@/design-system/format/number";

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
