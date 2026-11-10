/**
 * Give an area the signed-in account, or send the person to sign-in. A session that ended in the
 * middle of a task (`401` on any request) returns to the same page after sign-in; a sign-out does
 * not. Checking the session is not a permission check: `backend` answers each request for the
 * role (UI-40).
 */
import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect } from "react";
import { Navigate, useLocation } from "react-router";

import { PageColumn } from "@/design-system";
import { FailureState, getRequestFailure } from "@/features/backend-requests";
import { forgetAccountData } from "@/features/session/api/session-cache";
import { useCurrentSession } from "@/features/session/api/use-current-session";
import { SessionLoading } from "@/features/session/components/session-loading";
import type { Session } from "@/features/session/model/session";
import { buildSignInPath } from "@/features/session/model/sign-in-paths";

/** Props of {@link RequireSession}. */
export type RequireSessionProps = {
  /** Renders the area for the signed-in account. */
  readonly children: (session: Session) => ReactNode;
};

/** Props of {@link LeaveForSignIn}. */
type LeaveForSignInProps = {
  /** The sign-in path, with its return path when there is one. */
  readonly to: string;
};

/**
 * Render the area for the signed-in account.
 *
 * @param props - The render function of the area.
 * @returns The area, the loading or error state, or a redirect to sign-in.
 */
export function RequireSession({ children }: RequireSessionProps) {
  const sessionQuery = useCurrentSession();
  const location = useLocation();

  if (sessionQuery.data !== undefined) {
    const state = sessionQuery.data;
    if (state.kind === "signed_in") {
      return children(state.session);
    }
    const returnTo =
      state.reason === "no_valid_session"
        ? `${location.pathname}${location.search}${location.hash}`
        : undefined;
    return <LeaveForSignIn to={buildSignInPath(returnTo)} />;
  }
  const failure = getRequestFailure(sessionQuery.error);
  if (failure === undefined) {
    return <SessionLoading />;
  }
  return (
    <PageColumn area="shop">
      <FailureState
        title="Your session could not be checked"
        headingLevel={1}
        failure={failure}
        isRetrying={sessionQuery.isFetching}
        onRetry={() => {
          void sessionQuery.refetch();
        }}
      />
    </PageColumn>
  );
}

/**
 * Leave the area for sign-in. The screens of the account are already unmounted when the effect
 * runs, so removing their cached data cannot make them load it again (TS-22: the query cache is
 * an external system).
 *
 * @param props - The sign-in path.
 * @returns The redirect.
 */
function LeaveForSignIn({ to }: LeaveForSignInProps) {
  const queryClient = useQueryClient();
  useEffect(() => {
    forgetAccountData(queryClient);
  }, [queryClient]);
  return <Navigate to={to} replace />;
}
