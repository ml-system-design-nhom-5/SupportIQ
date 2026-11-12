/**
 * Read and change the queue that the inbox shows: the `status` search parameter of the address
 * (console UI design, Inbox). The inbox and the screen next to it read the same value, so both
 * show the same queue, and the queue stays when a ticket opens and after a reload.
 */
import { useSearchParams } from "react-router";

import { QUEUE_STATUS_PARAMETER } from "@/features/console-tickets/model/console-paths";
import {
  getQueueStatuses,
  parseQueueStatus,
  type QueueStatus,
} from "@/features/console-tickets/model/queue";
import { useSignedInRole } from "@/features/session";

/** The queue of the address, the queues of the role, and the function that changes the queue. */
export type QueueStatusState = {
  readonly status: QueueStatus;
  readonly statuses: readonly QueueStatus[];
  readonly changeStatus: (status: QueueStatus) => void;
};

/**
 * Read the queue status.
 *
 * @returns The status of the address when the role has its queue, otherwise Open; the queues of
 *   the role; and the function that changes the status and keeps the open ticket.
 */
export function useQueueStatus(): QueueStatusState {
  const [searchParams, setSearchParams] = useSearchParams();
  const statuses = getQueueStatuses(useSignedInRole() ?? "unknown");
  return {
    status: parseQueueStatus(searchParams.get(QUEUE_STATUS_PARAMETER), statuses),
    statuses,
    changeStatus: (status) => {
      setSearchParams(status === "open" ? {} : { [QUEUE_STATUS_PARAMETER]: status });
    },
  };
}
