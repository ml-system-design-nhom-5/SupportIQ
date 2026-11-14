/**
 * The public API of the console tickets feature (console UI design): the inbox with its area, the
 * prompt to select a ticket, the ticket workspace, the route of the workspace, and what the reports
 * share with it: the reason codes and the permission-denied state.
 */
export type { ConsolePermissionDeniedProps } from "@/features/console-tickets/components/console-permission-denied";
export { ConsolePermissionDenied } from "@/features/console-tickets/components/console-permission-denied";
export type { ConsoleTicketsAreaProps } from "@/features/console-tickets/components/console-tickets-area";
export { ConsoleTicketsArea } from "@/features/console-tickets/components/console-tickets-area";
export { NoTicketSelected } from "@/features/console-tickets/components/no-ticket-selected";
export type { TicketWorkspacePageProps } from "@/features/console-tickets/components/ticket-workspace-page";
export { TicketWorkspacePage } from "@/features/console-tickets/components/ticket-workspace-page";
export { TICKET_ID_PARAMETER, TICKET_ROUTE } from "@/features/console-tickets/model/console-paths";
export { toAiReasonCode } from "@/features/console-tickets/model/reason-codes";
export type { ShownStaffReasonCode } from "@/features/console-tickets/model/staff-reason-codes";
export {
  shownStaffReasonCodeLabels,
  toStaffReasonCodes,
} from "@/features/console-tickets/model/staff-reason-codes";
