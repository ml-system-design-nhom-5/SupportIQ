/**
 * The workspace when the ticket could not load (UI-25; console UI design, state-error.png and
 * state-permission-denied.png): "permission denied" for `403`, "not found" for `404`, otherwise the
 * error state with Try again. Each says what to do next and offers the copyable trace ID.
 */
import { Lock, SearchX } from "lucide-react";

import { CenteredContent, StateMessage } from "@/design-system";
import { describeFailure, FailureState, type RequestFailure } from "@/features/backend-requests";

/** Props of {@link WorkspaceLoadFailure}. */
type WorkspaceLoadFailureProps = {
  readonly failure: RequestFailure;
  readonly isRetrying: boolean;
  readonly onRetry: () => void;
};

/**
 * Render the failure of the ticket.
 *
 * @param props - The failure and its retry.
 * @returns The state message in the middle of the workspace.
 */
export function WorkspaceLoadFailure({ failure, isRetrying, onRetry }: WorkspaceLoadFailureProps) {
  const { category, traceId } = describeFailure(failure);
  const traceIdProps = traceId === undefined ? {} : { traceId };
  return (
    <CenteredContent>
      <title>Ticket · Console · SupportIQ</title>
      {category === "permission_denied" ? (
        <StateMessage
          icon={Lock}
          headingLevel={1}
          title="You cannot open this ticket"
          description="Your role does not allow it. Ask a manager if you need it."
          {...traceIdProps}
        />
      ) : null}
      {category === "not_found" ? (
        <StateMessage
          icon={SearchX}
          headingLevel={1}
          title="This ticket was not found"
          description="Choose a ticket in the inbox."
          {...traceIdProps}
        />
      ) : null}
      {category === "permission_denied" || category === "not_found" ? null : (
        <FailureState
          title="This ticket could not be loaded"
          failure={failure}
          headingLevel={1}
          isRetrying={isRetrying}
          onRetry={onRetry}
        />
      )}
    </CenteredContent>
  );
}
