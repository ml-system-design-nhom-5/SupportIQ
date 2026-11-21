import { describe, expect, it } from "vitest";

import { reportQueryKeys } from "@/features/console-reports/api/report-query-keys";

describe("reportQueryKeys", () => {
  it("builds one key per period under the feature's root key (TS-19)", () => {
    const period = { startAt: "2026-10-30T00:00:00.000Z", endAt: "2026-11-06T00:00:00.000Z" };

    expect(reportQueryKeys.report(period)).toEqual([
      "console-reports",
      "reports",
      "2026-10-30T00:00:00.000Z",
      "2026-11-06T00:00:00.000Z",
    ]);
  });
});
