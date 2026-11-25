/**
 * The error state of the report below the header (UI-23, UI-25): what happened, what to do next,
 * and the copyable trace ID when there is one. A manager only chooses a period, so a `422` gets
 * the page's own sentence, which points to the period menu in the header instead of Try again:
 * the same period would be refused again. Every other failure offers Try again.
 */
import { TriangleAlert } from "lucide-react";

import { StateMessage } from "@/design-system";
import { describeFailure, FailureState, type RequestFailure } from "@/features/backend-requests";

/** The heading of every error state of the report. */
const REPORT_FAILURE_TITLE = "The report could not be loaded";

/** What a `422` of the report means for a manager, and what to do next. */
const INVALID_PERIOD_TEXT = "This period could not be reported. Choose another period.";

/** Props of {@link ReportLoadFailure}. */
type ReportLoadFailureProps = {
  readonly failure: RequestFailure;
  /** True while the report loads again. */
  readonly isRetrying: boolean;
  /** Loads the report again. */
  readonly onRetry: () => void;
};

/**
 * Render the failure of the report.
 *
 * @param props - The failure and its retry.
 * @returns The state message, with a heading of level 2 below the page header.
 */
export function ReportLoadFailure({ failure, isRetrying, onRetry }: ReportLoadFailureProps) {
  const { category, traceId } = describeFailure(failure);
  if (category === "invalid_request") {
    return (
      <StateMessage
        icon={TriangleAlert}
        headingLevel={2}
        title={REPORT_FAILURE_TITLE}
        description={INVALID_PERIOD_TEXT}
        {...(traceId === undefined ? {} : { traceId })}
      />
    );
  }
  return (
    <FailureState
      title={REPORT_FAILURE_TITLE}
      failure={failure}
      headingLevel={2}
      isRetrying={isRetrying}
      onRetry={onRetry}
    />
  );
}
