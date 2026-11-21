import { describe, expect, it } from "vitest";

import { canReadReports } from "@/features/console-reports/model/reports-access";
import type { AccountRole } from "@/features/session";

describe("canReadReports", () => {
  it("lets a manager read the report", () => {
    expect(canReadReports("manager")).toBe(true);
  });

  it.each<AccountRole>(["staff", "admin", "customer", "unknown"])(
    "keeps the report from %s (ADR-0012)",
    (role) => {
      expect(canReadReports(role)).toBe(false);
    },
  );
});
