/**
 * A message in the inbox column instead of tickets, such as "No open tickets" (console UI design,
 * inbox-empty.png), or the error state of the queue.
 */
import type { ReactNode } from "react";

/** Props of {@link InboxMessage}. */
export type InboxMessageProps = {
  readonly children: ReactNode;
};

/**
 * Render the message with the padding of the inbox.
 *
 * @param props - The message.
 * @returns The padded message.
 */
export function InboxMessage({ children }: InboxMessageProps) {
  return <div className="flex flex-col gap-3 px-4 py-6">{children}</div>;
}
