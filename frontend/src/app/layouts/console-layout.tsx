/**
 * The console app shell of the console UI design, with the account menu and no ticket features yet:
 * the console operations are not in the contract (contracts v1 design, Rollout). No operation answers
 * `403` yet, so the shell opens for every signed-in role.
 */
import { Inbox } from "lucide-react";

import { PRODUCT_NAME } from "@/app/area-names";
import { AppBar, PageColumn, StateMessage } from "@/design-system";
import { RequireSession, SessionAccountMenu } from "@/features/session";

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
            account={<SessionAccountMenu session={session} variant="console" />}
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
