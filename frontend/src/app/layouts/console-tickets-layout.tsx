/**
 * The layout of the ticket screens of the console: the inbox next to the selected ticket, or next
 * to the prompt to select one (console UI design, Layout).
 */
import { Outlet } from "react-router";

import { ConsoleTicketsArea } from "@/features/console-tickets";

/**
 * Render the inbox around the current ticket screen.
 *
 * @returns The inbox and the screen.
 */
export function ConsoleTicketsLayout() {
  return (
    <ConsoleTicketsArea>
      <Outlet />
    </ConsoleTicketsArea>
  );
}
