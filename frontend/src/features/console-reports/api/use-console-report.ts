/**
 * Read the report of a period (`getConsoleReport`, FR-10). The read changes nothing. A report is
 * stale as soon as it arrives, so it is read again each time its period is shown: when the page
 * opens, when a manager chooses the period, and when the connection comes back. A period chosen
 * again shows the report already read, while it is still cached, until the new one arrives. It is
 * never read again on window focus or at an interval.
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
