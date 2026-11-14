/**
 * The navigation of the console app bar (console UI design, Layout): Tickets for every console
 * role, and Reports for managers only (UI-44); staff never see the link. Tickets is current on
 * every console page except Reports, whose path lies below its own.
 */
import { ChartColumn, Inbox } from "lucide-react";
import { useMatch } from "react-router";

import { NavItem } from "@/design-system";
import { REPORTS_PATH } from "@/features/console-reports";
import { type AccountRole, rootPathByArea } from "@/features/session";

/** Props of {@link ConsoleNavigation}. */
export type ConsoleNavigationProps = {
  readonly role: AccountRole;
};

/**
 * Render the navigation entries of a console role.
 *
 * @param props - The role of the signed-in account.
 * @returns Tickets, and Reports for a manager.
 */
export function ConsoleNavigation({ role }: ConsoleNavigationProps) {
  const isReportsOpen = useMatch(REPORTS_PATH) !== null;
  return (
    <>
      <NavItem to={rootPathByArea.console} icon={Inbox} isCurrent={!isReportsOpen}>
        Tickets
      </NavItem>
      {role === "manager" ? (
        <NavItem to={REPORTS_PATH} icon={ChartColumn}>
          Reports
        </NavItem>
      ) : null}
    </>
  );
}
