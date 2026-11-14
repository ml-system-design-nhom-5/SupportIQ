import { describe, expect, it } from "vitest";

import { formatDuration } from "@/design-system/format/duration";

describe("formatDuration", () => {
  it.each([
    [0, "0 s"],
    [3600, "3.6 s"],
    [4000, "4 s"],
    [9800, "9.8 s"],
    [10_800, "10.8 s"],
    [59_949, "59.9 s"],
    // 59.95 s rounds to a whole minute, so it is written in minutes.
    [59_950, "1 min 00 s"],
    [60_000, "1 min 00 s"],
    [130_000, "2 min 10 s"],
    [185_000, "3 min 05 s"],
    [1_050_000, "17 min 30 s"],
    [7_200_000, "120 min 00 s"],
    [60_000_000, "1,000 min 00 s"],
  ])("formats %i ms as %s", (durationMs, text) => {
    expect(formatDuration(durationMs)).toBe(text);
  });
});
