/**
 * The start page (`/`): it opens the area of the signed-in role, or sign-in. A role that this
 * version does not know has no area, and the page says so (contract, `AccountRole`).
 */
import { CircleHelp } from "lucide-react";
import { Navigate } from "react-router";

import { PageColumn, StateMessage } from "@/design-system";
import { RequireSession } from "@/features/session/components/require-session";
import { SignOutButton } from "@/features/session/components/sign-out-button";
import { getRoleArea, rootPathByArea } from "@/features/session/model/session";

/**
 * Render the start page.
 *
 * @returns A redirect to the role's area, or the no-area state.
 */
export function StartPage() {
  return (
    <RequireSession>
      {(session) => {
        const area = getRoleArea(session.role);
        if (area !== "none") {
          return <Navigate to={rootPathByArea[area]} replace />;
        }
        return (
          <PageColumn area="shop">
            <title>SupportIQ</title>
            <StateMessage
              icon={CircleHelp}
              headingLevel={1}
              title="This account has no area in this version"
              description="Sign out, then sign in with a customer, support, or admin account."
              actions={<SignOutButton placement="state" />}
            />
          </PageColumn>
        );
      }}
    </RequireSession>
  );
}
