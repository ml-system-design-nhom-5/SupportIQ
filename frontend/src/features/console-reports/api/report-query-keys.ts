/**
 * The query keys of the console reports feature (TS-19).
 */
import type { ReportPeriod } from "@/features/console-reports/model/report-period";

/** The one key factory of the console reports feature. */
export const reportQueryKeys = {
  all: ["console-reports"] as const,
  /** The report of one period: each period is cached on its own. */
  report: (period: ReportPeriod) =>
    [...reportQueryKeys.all, "reports", period.startAt, period.endAt] as const,
};
