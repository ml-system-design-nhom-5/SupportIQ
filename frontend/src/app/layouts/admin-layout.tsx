/**
 * The admin app shell (admin UI design, Layout): the console app shell with "SupportIQ Admin", the
 * navigation, the admin's display name, and Sign out. The Versions screen is not built yet,
 * because `getAdminVersions` is not in the contract (admin UI design, Rollout). A session of
 * another role sees only the brand: every admin operation answers it with `403`.
 */
import { Users } from "lucide-react";
import { Outlet } from "react-router";

import { PRODUCT_NAME } from "@/app/area-names";
import { AccountLabel, AppBar, NavItem, PageColumn } from "@/design-system";
import { ACCOUNTS_PATH } from "@/features/admin-accounts";
import { getRoleLabel, RequireSession, SignOutButton } from "@/features/session";

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
                <NavItem to={ACCOUNTS_PATH} icon={Users}>
                  Accounts
                </NavItem>
              }
              account={
                <>
                  <AccountLabel
                    displayName={session.displayName}
                    roleLabel={getRoleLabel(session.role)}
                  />
                  <SignOutButton placement="app-bar" />
                </>
              }
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
