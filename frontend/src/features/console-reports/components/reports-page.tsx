/**
 * The Reports page of managers (`/console/reports`; console UI design, Reports; FR-10, UI-44):
 * the figures that `backend` returns for a chosen period, each with its unit and its target. The
 * period menu sits in the header, and choosing a period loads its report. A role other than
 * manager sees the permission-denied state at once, and the page sends no request. `backend`
 * stays the check: a `403` for a manager shows the same state (UI-40, SEC-20).
 */
import type { UseQueryResult } from "@tanstack/react-query";
import { useState } from "react";

import { MenuSelect, PageColumn, PageHeader, useNow } from "@/design-system";
import {
  categorizeFailure,
  getRequestFailure,
  type RequestFailure,
} from "@/features/backend-requests";
import { useConsoleReport } from "@/features/console-reports/api/use-console-report";
import { ReportGrid } from "@/features/console-reports/components/report-grid";
import { ReportLoadFailure } from "@/features/console-reports/components/report-load-failure";
import { ReportsLoading } from "@/features/console-reports/components/reports-loading";
import { ReportsPermissionDenied } from "@/features/console-reports/components/reports-permission-denied";
import type { ConsoleReport } from "@/features/console-reports/model/report";
import {
  buildReportPeriod,
  DEFAULT_REPORT_PERIOD_PRESET,
  reportPeriodOptions,
  type ReportPeriodPreset,
} from "@/features/console-reports/model/report-period";
import { canReadReports } from "@/features/console-reports/model/reports-access";
import { useSignedInRole } from "@/features/session";

/** The title of the browser tab. */
const DOCUMENT_TITLE = "Reports · Console · SupportIQ";

/** Props of {@link DeniedReportsPage}. */
type DeniedReportsPageProps = {
  /** The `403` of the report; absent when the page sent no request for the role. */
  readonly failure?: RequestFailure;
};

/** Props of {@link ReportContent}. */
type ReportContentProps = {
  readonly query: UseQueryResult<ConsoleReport>;
};

/**
 * Render the Reports page for the signed-in role.
 *
 * @returns The page of a manager, or the permission-denied state without a request.
 */
export function ReportsPage() {
  const role = useSignedInRole();
  return role !== undefined && canReadReports(role) ? (
    <ManagerReportsPage />
  ) : (
    <DeniedReportsPage />
  );
}

/**
 * Render the page of a manager, which reads the report of the chosen period.
 *
 * @returns The page in the state of its report.
 */
function ManagerReportsPage() {
  const now = useNow();
  const [preset, setPreset] = useState<ReportPeriodPreset>(DEFAULT_REPORT_PERIOD_PRESET);
  const reportQuery = useConsoleReport(buildReportPeriod(preset, now));
  const failure = getRequestFailure(reportQuery.error);
  if (failure !== undefined && categorizeFailure(failure) === "permission_denied") {
    return <DeniedReportsPage failure={failure} />;
  }
  return (
    <PageColumn area="console">
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
    </PageColumn>
  );
}

/**
 * Render the page without the report: no header and no period menu.
 *
 * @param props - The refusal of `backend`, when there was one.
 * @returns The permission-denied state.
 */
function DeniedReportsPage({ failure }: DeniedReportsPageProps) {
  return (
    <PageColumn area="console">
      <title>{DOCUMENT_TITLE}</title>
      <ReportsPermissionDenied {...(failure === undefined ? {} : { failure })} />
    </PageColumn>
  );
}

/**
 * Render the report of the chosen period: its figures, its loading state, or its error state
 * (UI-23, UI-25).
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
      <ReportLoadFailure
        failure={failure}
        isRetrying={query.isFetching}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  return <ReportsLoading />;
}
