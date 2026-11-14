/**
 * The Reports page of managers (`/console/reports`; console UI design, Reports; FR-10, UI-44):
 * the figures that `backend` returns for a chosen period, each with its unit and its target. The
 * period menu sits in the header, and choosing a period loads its report. `backend` decides who
 * may read the report: a `403` shows the permission-denied state (UI-40).
 */
import type { UseQueryResult } from "@tanstack/react-query";
import { useState } from "react";

import { ConsolePage, MenuSelect, PageHeader, useNow } from "@/design-system";
import { categorizeFailure, FailureState, getRequestFailure } from "@/features/backend-requests";
import { useConsoleReport } from "@/features/console-reports/api/use-console-report";
import { ReportGrid } from "@/features/console-reports/components/report-grid";
import { ReportsLoading } from "@/features/console-reports/components/reports-loading";
import { ReportsPermissionDenied } from "@/features/console-reports/components/reports-permission-denied";
import type { ConsoleReport } from "@/features/console-reports/model/report";
import {
  buildReportPeriod,
  DEFAULT_REPORT_PERIOD_PRESET,
  reportPeriodOptions,
  type ReportPeriodPreset,
} from "@/features/console-reports/model/report-period";

/** The title of the browser tab. */
const DOCUMENT_TITLE = "Reports · Console · SupportIQ";

/** Props of {@link ReportContent}. */
type ReportContentProps = {
  readonly query: UseQueryResult<ConsoleReport>;
};

/**
 * Render the Reports page.
 *
 * @returns The page in the state of its report.
 */
export function ReportsPage() {
  const now = useNow();
  const [preset, setPreset] = useState<ReportPeriodPreset>(DEFAULT_REPORT_PERIOD_PRESET);
  const reportQuery = useConsoleReport(buildReportPeriod(preset, now));
  const failure = getRequestFailure(reportQuery.error);
  if (failure !== undefined && categorizeFailure(failure) === "permission_denied") {
    return (
      <ConsolePage>
        <title>{DOCUMENT_TITLE}</title>
        <ReportsPermissionDenied failure={failure} />
      </ConsolePage>
    );
  }
  return (
    <ConsolePage>
      <title>{DOCUMENT_TITLE}</title>
      <PageHeader
        title="Reports"
        density="compact"
        meta={reportQuery.data?.periodText}
        action={
          <MenuSelect
            label="Report period"
            options={reportPeriodOptions}
            value={preset}
            onChange={setPreset}
          />
        }
      />
      <ReportContent query={reportQuery} />
    </ConsolePage>
  );
}

/**
 * Render the report of the chosen period: its figures, its loading state, or its error state
 * with Try again and the trace ID (UI-23, UI-25).
 *
 * @param props - The query of the report.
 * @returns The content below the header.
 */
function ReportContent({ query }: ReportContentProps) {
  if (query.data !== undefined) {
    return <ReportGrid sections={query.data.sections} />;
  }
  const failure = getRequestFailure(query.error);
  if (failure !== undefined) {
    return (
      <FailureState
        title="The report could not be loaded"
        failure={failure}
        headingLevel={2}
        isRetrying={query.isFetching}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  return <ReportsLoading />;
}
