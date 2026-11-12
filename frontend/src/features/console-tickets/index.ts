/**
 * The public API of the console tickets feature (console UI design): the inbox with its area, the
 * prompt to select a ticket, the ticket workspace, and the route of the workspace.
 */
export type { ConsoleTicketsAreaProps } from "@/features/console-tickets/components/console-tickets-area";
export { ConsoleTicketsArea } from "@/features/console-tickets/components/console-tickets-area";
export { NoTicketSelected } from "@/features/console-tickets/components/no-ticket-selected";
export type { TicketWorkspacePageProps } from "@/features/console-tickets/components/ticket-workspace-page";
export { TicketWorkspacePage } from "@/features/console-tickets/components/ticket-workspace-page";
export { TICKET_ID_PARAMETER, TICKET_ROUTE } from "@/features/console-tickets/model/console-paths";
