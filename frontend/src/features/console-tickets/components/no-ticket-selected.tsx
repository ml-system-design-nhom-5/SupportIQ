/**
 * The screen next to the inbox when no ticket is selected (console UI design, no-ticket-selected.png
 * and inbox-empty.png): a prompt to select a ticket, or the empty state of the queue.
 */
import { CircleCheck, Inbox } from "lucide-react";

import { CenteredContent, StateMessage } from "@/design-system";
import { useTicketQueue } from "@/features/console-tickets/api/use-ticket-queue";
import { useQueueStatus } from "@/features/console-tickets/components/use-queue-status";
import { getEmptyQueueText, getQueueOrderLabel } from "@/features/console-tickets/model/queue";

/**
 * Render the prompt. It reads the same queue as the inbox, from the same cache.
 *
 * @returns The state message.
 */
export function NoTicketSelected() {
  const { status } = useQueueStatus();
  const { data } = useTicketQueue(status);
  const isQueueEmpty = data?.pages.every((page) => page.tickets.length === 0) === true;
  return (
    <CenteredContent>
      <title>Tickets · Console · SupportIQ</title>
      {isQueueEmpty ? (
        <StateMessage
          icon={CircleCheck}
          headingLevel={1}
          title={getEmptyQueueText(status)}
          description="New tickets appear here on their own."
        />
      ) : (
        <StateMessage
          icon={Inbox}
          headingLevel={1}
          title="Select a ticket"
          description={`Tickets wait in the inbox, ${getQueueOrderLabel(status).toLowerCase()}.`}
        />
      )}
    </CenteredContent>
  );
}
