/**
 * The route element of the ticket workspace: it reads the ticket ID from the address. The key
 * opens each ticket anew, so its view is recorded once each time it opens and no state of one
 * ticket reaches another (console UI design, Observability).
 */
import { useRouteParam } from "@/app/routes/route-params";
import { TICKET_ID_PARAMETER, TicketWorkspacePage } from "@/features/console-tickets";

/**
 * Render the workspace of the ticket in the address.
 *
 * @returns The workspace.
 */
export function TicketRoute() {
  const ticketId = useRouteParam(TICKET_ID_PARAMETER);
  return <TicketWorkspacePage key={ticketId} ticketId={ticketId} />;
}
