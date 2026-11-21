/**
 * The admin app shell (admin UI design, Layout): the console app shell with "SupportIQ Admin", the
 * navigation Accounts and Versions, and the account menu with Change password and Sign out. A
 * session of another role sees only the brand: every admin operation answers it with `403`.
 */
import { Layers, Users } from "lucide-react";
import { Outlet } from "react-router";

import { PRODUCT_NAME } from "@/app/area-names";
import { AppBar, NavItem, PageColumn } from "@/design-system";
import { ACCOUNTS_PATH } from "@/features/admin-accounts";
import { VERSIONS_PATH } from "@/features/admin-versions";
import { RequireSession, SessionAccountMenu } from "@/features/session";

/**
 * Render the admin shell around the current admin screen.
 *
 * @returns The shell, or the session's loading, error, or sign-in redirect.
 */
export function AdminLayout() {
  return (
    <RequireSession>
      {(session) => (
        <>
          {session.role === "admin" ? (
            <AppBar
              variant="console"
              brandName={PRODUCT_NAME}
              areaName="Admin"
              navigation={
                <>
                  <NavItem to={ACCOUNTS_PATH} icon={Users}>
                    Accounts
                  </NavItem>
                  <NavItem to={VERSIONS_PATH} icon={Layers}>
                    Versions
                  </NavItem>
                </>
              }
              account={<SessionAccountMenu session={session} variant="console" />}
            />
          ) : (
            <AppBar variant="console" brandName={PRODUCT_NAME} areaName="Admin" />
          )}
          <PageColumn area="admin">
            <Outlet />
          </PageColumn>
        </>
      )}
    </RequireSession>
  );
}
