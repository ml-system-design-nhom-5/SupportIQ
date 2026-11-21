import { describe, expect, it } from "vitest";

import { formatDuration } from "@/design-system";
import {
  formatCountOf,
  formatOptional,
  NO_DATA_TEXT,
} from "@/features/console-reports/model/report-units";

describe("formatCountOf", () => {
  it.each([
    [0, "ticket", "0 tickets"],
    [1, "ticket", "1 ticket"],
    [2, "ticket", "2 tickets"],
    [1, "reply", "1 reply"],
    [52, "reply", "52 replies"],
    [1, "escalation", "1 escalation"],
    [0, "escalation", "0 escalations"],
    [1, "suggestion", "1 suggestion"],
    [1200, "suggestion", "1,200 suggestions"],
  ] as const)("formats %i of the unit %s as %s", (count, unit, text) => {
    expect(formatCountOf(count, unit)).toBe(text);
  });
});

describe("formatOptional", () => {
  it("says No data for a figure that backend left out", () => {
    expect(formatOptional(undefined, formatDuration)).toBe(NO_DATA_TEXT);
    expect(NO_DATA_TEXT).toBe("No data");
  });

  it("formats a figure of 0, which is a value and not missing data", () => {
    expect(formatOptional(0, formatDuration)).toBe("0 s");
  });
});
