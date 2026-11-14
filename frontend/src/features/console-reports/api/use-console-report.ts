/**
 * Read the report of a period (`getConsoleReport`, FR-10). The read changes nothing, and it never
 * loads again by itself: a manager chooses a period, and each period is read once.
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { useBackendClient } from "@/api/client";
import { requestData } from "@/features/backend-requests";
import { reportQueryKeys } from "@/features/console-reports/api/report-query-keys";
import { type ConsoleReport, toConsoleReport } from "@/features/console-reports/model/report";
import type { ReportPeriod } from "@/features/console-reports/model/report-period";

/**
 * Read the report.
 *
 * @param period - The start, included, and the end, excluded, as UTC timestamps.
 * @returns The query of the report.
 */
export function useConsoleReport(period: ReportPeriod): UseQueryResult<ConsoleReport> {
  const client = useBackendClient();
  return useQuery({
    queryKey: reportQueryKeys.report(period),
    queryFn: ({ signal }) =>
      requestData(
        () =>
          client.GET("/v1/console/reports", {
            params: { query: { start_at: period.startAt, end_at: period.endAt } },
            signal,
          }),
        toConsoleReport,
      ),
  });
}
