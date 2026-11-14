/**
 * The workspace when the ticket could not load (UI-25; console UI design, States): one
 * permission-denied state for `403` and `404` (state-permission-denied.png), otherwise the error
 * state with Try again (state-error.png). Each says what to do next and offers the copyable trace
 * ID.
 */
import { CenteredContent } from "@/design-system";
import { describeFailure, FailureState, type RequestFailure } from "@/features/backend-requests";
import { ConsolePermissionDenied } from "@/features/console-tickets/components/console-permission-denied";

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
      {category === "permission_denied" || category === "not_found" ? (
        <ConsolePermissionDenied {...traceIdProps} />
      ) : (
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
