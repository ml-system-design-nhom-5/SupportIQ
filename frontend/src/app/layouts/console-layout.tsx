/**
 * The console app shell of the console UI design, with Sign out and no ticket features yet: the
 * console operations are not in the contract (contracts v1 design, Rollout). No operation answers
 * `403` yet, so the shell opens for every signed-in role.
 */
import { Inbox } from "lucide-react";

import { PRODUCT_NAME } from "@/app/area-names";
import { AccountLabel, AppBar, PageColumn, StateMessage } from "@/design-system";
import { getRoleLabel, RequireSession, SignOutButton } from "@/features/session";

/**
 * Render the console shell.
 *
 * @returns The shell with a note that the ticket features come later.
 */
export function ConsoleLayout() {
  return (
    <RequireSession>
      {(session) => (
        <>
          <title>Console · SupportIQ</title>
          <AppBar
            variant="console"
            brandName={PRODUCT_NAME}
            areaName="Console"
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
          <PageColumn area="admin">
            <StateMessage
              icon={Inbox}
              headingLevel={1}
              title="The ticket inbox is not available yet"
              description="The console screens come in a later version of SupportIQ."
            />
          </PageColumn>
        </>
      )}
    </RequireSession>
  );
}
