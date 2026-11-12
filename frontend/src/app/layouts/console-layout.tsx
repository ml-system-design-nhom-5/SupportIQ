/**
 * The console app shell (console UI design, Layout): the app bar with "SupportIQ Console", the
 * navigation, and the account menu, above the screen of the console at the height of the window.
 * A session of a role without the console sees only the brand, as in the admin area: `backend`
 * answers every console operation with `403`, and the screen shows the permission-denied state
 * with Sign out (UI-40).
 */
import { Inbox } from "lucide-react";
import { Outlet } from "react-router";

import { PRODUCT_NAME } from "@/app/area-names";
import { AppBar, ConsoleShell, NavItem } from "@/design-system";
import {
  getRoleArea,
  RequireSession,
  rootPathByArea,
  SessionAccountMenu,
} from "@/features/session";

/**
 * Render the console shell around the current console screen.
 *
 * @returns The shell, or the session's loading, error, or sign-in redirect.
 */
export function ConsoleLayout() {
  return (
    <RequireSession>
      {(session) => (
        <ConsoleShell
          appBar={
            getRoleArea(session.role) === "console" ? (
              <AppBar
                variant="console"
                brandName={PRODUCT_NAME}
                areaName="Console"
                navigation={
                  <NavItem to={rootPathByArea.console} icon={Inbox}>
                    Tickets
                  </NavItem>
                }
                account={<SessionAccountMenu session={session} variant="console" />}
              />
            ) : (
              <AppBar variant="console" brandName={PRODUCT_NAME} areaName="Console" />
            )
          }
        >
          <Outlet />
        </ConsoleShell>
      )}
    </RequireSession>
  );
}
