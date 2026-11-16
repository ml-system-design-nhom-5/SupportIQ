/**
 * The public API of the console tickets feature (console UI design): the inbox with its area, the
 * prompt to select a ticket, the ticket workspace, the route of the workspace, the opener of the
 * suggestion progress stream that the composition root provides, and the reason codes that the
 * reports show too.
 */
export type {
  OpenEventSource,
  SuggestionEventSource,
} from "@/features/console-tickets/api/suggestion-events";
export { EventSourceContext } from "@/features/console-tickets/api/suggestion-events";
export type { ConsoleTicketsAreaProps } from "@/features/console-tickets/components/console-tickets-area";
export { ConsoleTicketsArea } from "@/features/console-tickets/components/console-tickets-area";
export { NoTicketSelected } from "@/features/console-tickets/components/no-ticket-selected";
export type { TicketWorkspacePageProps } from "@/features/console-tickets/components/ticket-workspace-page";
export { TicketWorkspacePage } from "@/features/console-tickets/components/ticket-workspace-page";
export { TICKET_ID_PARAMETER, TICKET_ROUTE } from "@/features/console-tickets/model/console-paths";
export { toAiReasonCode } from "@/features/console-tickets/model/reason-codes";
export {
  shownStaffReasonCodeLabels,
  toStaffReasonCode,
} from "@/features/console-tickets/model/staff-reason-codes";
