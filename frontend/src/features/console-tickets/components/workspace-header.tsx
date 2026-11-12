/**
 * The ticket header of the workspace (console UI design, Workspace regions): the badges of the
 * ticket, the order chip or "No order attached", the customer, and the time received.
 */
import {
  presentationByConsoleTicketStatus,
  presentationByHandlingMode,
  Text,
  TicketHeader,
} from "@/design-system";
import { TicketOrderChip } from "@/features/console-tickets/components/ticket-order-chip";
import type { TicketWorkspace } from "@/features/console-tickets/model/workspace";

/** Props of {@link WorkspaceHeader}. */
type WorkspaceHeaderProps = {
  /** The ID of the ticket heading. */
  readonly headingId: string;
  readonly workspace: TicketWorkspace;
  readonly isOrderOpen: boolean;
  readonly onOrderOpenChange: (isOpen: boolean) => void;
};

/**
 * Render the ticket header.
 *
 * @param props - The heading ID, the ticket, and the open state of its order popover.
 * @returns The header.
 */
export function WorkspaceHeader({
  headingId,
  workspace,
  isOrderOpen,
  onOrderOpenChange,
}: WorkspaceHeaderProps) {
  const order = workspace.order;
  return (
    <TicketHeader
      headingId={headingId}
      ticketId={workspace.ticketId}
      status={presentationByConsoleTicketStatus[workspace.status]}
      handlingMode={presentationByHandlingMode[workspace.handlingMode]}
      order={
        order === undefined ? (
          <Text tone="muted">No order attached</Text>
        ) : (
          <TicketOrderChip
            order={order}
            otherOrders={workspace.otherOrders}
            isOpen={isOrderOpen}
            onOpenChange={onOrderOpenChange}
          />
        )
      }
      customerName={workspace.customerName}
      receivedAt={workspace.createdAt}
    />
  );
}
