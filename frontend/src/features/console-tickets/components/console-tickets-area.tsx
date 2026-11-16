/**
 * The ticket screens of the console (console UI design, Layout): the inbox on the left and the
 * selected ticket, or the prompt to select one, on the right. When `backend` refuses the queue
 * with `403`, the account may not use the console, and the area shows the permission-denied state
 * instead (UI-40).
 */
import type { ReactNode } from "react";

import { InboxLayout, PageColumn } from "@/design-system";
import { categorizeFailure, describeFailure, getRequestFailure } from "@/features/backend-requests";
import { useResizableColumn } from "@/features/console-tickets/api/use-resizable-column";
import { useTicketQueue } from "@/features/console-tickets/api/use-ticket-queue";
import { TicketInbox } from "@/features/console-tickets/components/ticket-inbox";
import { useQueueStatus } from "@/features/console-tickets/components/use-queue-status";
import { AreaPermissionDenied } from "@/features/session";

/** Props of {@link ConsoleTicketsArea}. */
export type ConsoleTicketsAreaProps = {
  /** The screen next to the inbox. */
  readonly children: ReactNode;
};

/**
 * Render the inbox next to the screen.
 *
 * @param props - The screen next to the inbox.
 * @returns The two columns, or the permission-denied state.
 */
export function ConsoleTicketsArea({ children }: ConsoleTicketsAreaProps) {
  const { status, statuses, changeStatus } = useQueueStatus();
  const queueQuery = useTicketQueue(status);
  const inboxColumn = useResizableColumn("inbox");
  const failure = getRequestFailure(queueQuery.error);
  if (
    queueQuery.data === undefined &&
    failure !== undefined &&
    categorizeFailure(failure) === "permission_denied"
  ) {
    const { traceId } = describeFailure(failure);
    return (
      <PageColumn area="admin">
        <AreaPermissionDenied area="console" {...(traceId === undefined ? {} : { traceId })} />
      </PageColumn>
    );
  }
  return (
    <InboxLayout
      inbox={
        <TicketInbox
          status={status}
          statuses={statuses}
          onStatusChange={changeStatus}
          queueQuery={queueQuery}
          onCollapse={() => {
            inboxColumn.onChange({ width: inboxColumn.width, isCollapsed: true });
          }}
        />
      }
      inboxColumn={inboxColumn}
    >
      {children}
    </InboxLayout>
  );
}
