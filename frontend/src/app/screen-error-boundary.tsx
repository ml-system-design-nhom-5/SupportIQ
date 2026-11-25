/**
 * The error boundary of a screen inside an area shell (TS-26). The shell and its `main` region
 * stay; only the screen shows the error state.
 */
import { RotateCcw, TriangleAlert } from "lucide-react";
import { useRouteError } from "react-router";

import { Button, StateMessage } from "@/design-system";
import { describeFailure, getRequestFailure } from "@/features/backend-requests";

const FALLBACK_DESCRIPTION = "Something went wrong. Reload the page to try again.";

/**
 * Render the error state of a screen.
 *
 * @returns The error state, with Reload page and the trace ID when there is one.
 */
export function ScreenErrorBoundary() {
  const failure = getRequestFailure(useRouteError());
  const description = failure === undefined ? undefined : describeFailure(failure);
  return (
    <StateMessage
      icon={TriangleAlert}
      headingLevel={1}
      title="This page could not be shown"
      description={description?.message ?? FALLBACK_DESCRIPTION}
      {...(description?.traceId === undefined ? {} : { traceId: description.traceId })}
      actions={
        <Button
          leadingIcon={RotateCcw}
          onClick={() => {
            window.location.reload();
          }}
        >
          Reload page
        </Button>
      }
    />
  );
}
