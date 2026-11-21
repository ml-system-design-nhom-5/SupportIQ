/**
 * The query keys of the console tickets feature (TS-19).
 */
import type { QueueStatus } from "@/features/console-tickets/model/queue";

/** The one key factory of the console tickets feature. */
export const consoleQueryKeys = {
  all: ["console-tickets"] as const,
  /** Every queue: invalidating it reloads the queue of every status. */
  queues: () => [...consoleQueryKeys.all, "queues"] as const,
  queue: (status: QueueStatus) => [...consoleQueryKeys.queues(), status] as const,
  workspace: (ticketId: string) => [...consoleQueryKeys.all, "workspaces", ticketId] as const,
  kbDocumentVersion: (documentId: string, version: string) =>
    [...consoleQueryKeys.all, "kb-document-versions", documentId, version] as const,
  /**
   * The mutation of Send reply. It is not an idempotent write of the composition root, so it never
   * retries (TS-29).
   */
  sendReply: (ticketId: string) => [...consoleQueryKeys.all, "send-reply", ticketId] as const,
};
