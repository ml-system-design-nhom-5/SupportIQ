/**
 * The inbox (console UI design, Inbox): the status dropdown, the order of the queue, and its
 * tickets, with the loading, empty, and error states (UI-23). The queue reloads on its own while
 * the inbox is open; a reload that fails keeps the tickets on screen and says so.
 */
import { Info, RefreshCw } from "lucide-react";

import {
  InboxItemSkeleton,
  InboxMessage,
  InboxPanel,
  InlineMessage,
  LoadMoreButton,
  MenuSelect,
  Stack,
  VisuallyHidden,
} from "@/design-system";
import {
  collectPageItems,
  describeFailure,
  FailureState,
  getRequestFailure,
} from "@/features/backend-requests";
import type { TicketQueueQuery } from "@/features/console-tickets/api/use-ticket-queue";
import { InboxTicket } from "@/features/console-tickets/components/inbox-ticket";
import {
  getEmptyQueueText,
  getQueueLabel,
  getQueueOrderLabel,
  type QueueStatus,
} from "@/features/console-tickets/model/queue";
import type { TicketSummary } from "@/features/console-tickets/model/ticket-summary";

/** The keys of the skeleton items that stand in for the first page. */
const skeletonItemKeys = ["first", "second", "third"] as const;

/** Props of {@link TicketInbox}. */
type TicketInboxProps = {
  readonly status: QueueStatus;
  readonly statuses: readonly QueueStatus[];
  readonly onStatusChange: (status: QueueStatus) => void;
  readonly queueQuery: TicketQueueQuery;
  readonly onCollapse: () => void;
};

/**
 * Render the inbox.
 *
 * @param props - The queue status, the queues of the role, the change handler, the query, and the
 *   collapse handler.
 * @returns The inbox panel.
 */
export function TicketInbox({
  status,
  statuses,
  onStatusChange,
  queueQuery,
  onCollapse,
}: TicketInboxProps) {
  return (
    <InboxPanel
      onCollapse={onCollapse}
      statusSelect={
        <MenuSelect
          label="Ticket status"
          options={statuses.map((option) => ({ value: option, label: getQueueLabel(option) }))}
          value={status}
          onChange={onStatusChange}
        />
      }
      orderLabel={getQueueOrderLabel(status)}
    >
      <QueueContent status={status} queueQuery={queueQuery} />
    </InboxPanel>
  );
}

/**
 * Render the tickets of the queue, or its state.
 *
 * @param props - The queue status and the query.
 * @returns The list, the skeleton, the error, or the empty message.
 */
function QueueContent({ status, queueQuery }: Pick<TicketInboxProps, "status" | "queueQuery">) {
  const failure = getRequestFailure(queueQuery.error);
  if (queueQuery.data === undefined) {
    return failure === undefined ? (
      <QueueLoading />
    ) : (
      <InboxMessage>
        <FailureState
          title="The inbox could not be loaded"
          failure={failure}
          headingLevel={2}
          isRetrying={queueQuery.isFetching}
          onRetry={() => {
            void queueQuery.refetch();
          }}
        />
      </InboxMessage>
    );
  }
  const tickets = collectPageItems(
    queueQuery.data.pages.map((page) => page.tickets),
    (ticket: TicketSummary) => ticket.ticketId,
  );
  if (tickets.length === 0) {
    return (
      <InboxMessage>
        <InlineMessage tone="muted" icon={Info}>
          {getEmptyQueueText(status)}
        </InlineMessage>
      </InboxMessage>
    );
  }
  return (
    <>
      {failure === undefined ? null : (
        <InboxMessage>
          <InlineMessage tone="danger" icon={RefreshCw} role="alert">
            The inbox could not be updated. {describeFailure(failure).message}
          </InlineMessage>
        </InboxMessage>
      )}
      <Stack as="ul" label={`${getQueueLabel(status)} tickets`}>
        {tickets.map((ticket) => (
          <InboxTicket key={ticket.ticketId} ticket={ticket} queueStatus={status} />
        ))}
      </Stack>
      {queueQuery.hasNextPage ? (
        <InboxMessage>
          <LoadMoreButton
            label="Show more tickets"
            size="md"
            isLoading={queueQuery.isFetchingNextPage}
            onLoadMore={() => {
              void queueQuery.fetchNextPage();
            }}
          />
        </InboxMessage>
      ) : null}
    </>
  );
}

/**
 * Render the loading state of the queue (UI-24).
 *
 * @returns Skeleton items.
 */
function QueueLoading() {
  return (
    <>
      <p role="status">
        <VisuallyHidden>Loading the tickets…</VisuallyHidden>
      </p>
      {skeletonItemKeys.map((key) => (
        <InboxItemSkeleton key={key} />
      ))}
    </>
  );
}
