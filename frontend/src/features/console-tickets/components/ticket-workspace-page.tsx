/**
 * The ticket workspace screen (`/console/tickets/{ticket_id}`, console UI design, Flow). Opening
 * it records the view, which starts the handling clock and can start a retry of a failed
 * suggestion, and then loads the workspace. The workspace polls while a part of the suggestion is
 * `pending`.
 */
import { getRequestFailure } from "@/features/backend-requests";
import { useRecordTicketView } from "@/features/console-tickets/api/use-record-ticket-view";
import { useTicketWorkspace } from "@/features/console-tickets/api/use-ticket-workspace";
import { TicketWorkspaceView } from "@/features/console-tickets/components/ticket-workspace-view";
import { WorkspaceLoadFailure } from "@/features/console-tickets/components/workspace-load-failure";
import { WorkspaceLoading } from "@/features/console-tickets/components/workspace-loading";

/** Props of {@link TicketWorkspacePage}. */
export type TicketWorkspacePageProps = {
  /** The ticket of the address. The route gives it as the key, so each ticket opens anew. */
  readonly ticketId: string;
};

/**
 * Render the workspace of a ticket in the state of its data.
 *
 * @param props - The ticket ID.
 * @returns The workspace, its loading state, or its failure state.
 */
export function TicketWorkspacePage({ ticketId }: TicketWorkspacePageProps) {
  const view = useRecordTicketView(ticketId);
  const workspaceQuery = useTicketWorkspace({ ticketId, isViewSettled: view.isSettled });
  const failure = getRequestFailure(workspaceQuery.error);
  if (workspaceQuery.data !== undefined) {
    return (
      <TicketWorkspaceView
        ticketId={ticketId}
        workspace={workspaceQuery.data}
        {...(view.failure === undefined ? {} : { viewFailure: view.failure })}
        {...(workspaceQuery.isRefetchError && failure !== undefined
          ? { refreshFailure: failure }
          : {})}
      />
    );
  }
  if (failure !== undefined) {
    return (
      <WorkspaceLoadFailure
        failure={failure}
        isRetrying={workspaceQuery.isFetching}
        onRetry={() => {
          void workspaceQuery.refetch();
        }}
      />
    );
  }
  return <WorkspaceLoading />;
}
