/**
 * Start and end a session in the query cache. The cached responses of an account are removed once
 * its screens have left, so the next account never sees them (ADR-0012: a role change applies at
 * once).
 */
import type { QueryClient } from "@tanstack/react-query";

import { isSessionQueryKey, sessionQueryKeys } from "@/features/session/api/session-query-keys";
import type { Session, SessionState, SignedOutReason } from "@/features/session/model/session";

/**
 * Remove the cached responses and the finished writes of the previous account. A query in flight
 * is cancelled silently, so a late `401` cannot end the next session. Call it only while no screen
 * of the account is mounted: a mounted screen would create its query again and send a request.
 *
 * @param queryClient - The query client of the app.
 */
export function forgetAccountData(queryClient: QueryClient): void {
  queryClient.removeQueries({ predicate: (query) => !isSessionQueryKey(query.queryKey) });
  queryClient.getMutationCache().clear();
}

/**
 * Record a new session after sign-in. It also forgets the data of any earlier account and every
 * sign-in attempt, each of which holds the password as its variables.
 *
 * @param queryClient - The query client of the app.
 * @param session - The account that signed in.
 */
export function startSession(queryClient: QueryClient, session: Session): void {
  forgetAccountData(queryClient);
  replaceCachedSession(queryClient, session);
}

/**
 * Replace the signed-in account with the one that `backend` returned, for example after the own
 * password change (account management design, Change password page). The account's data stays.
 *
 * @param queryClient - The query client of the app.
 * @param session - The signed-in account, as `backend` returned it.
 */
export function replaceCachedSession(queryClient: QueryClient, session: Session): void {
  const state: SessionState = { kind: "signed_in", session };
  queryClient.setQueryData(sessionQueryKeys.current(), state);
}

/**
 * End the session: after a sign-out, or when `backend` answers `401` to any request. The area
 * then leaves for sign-in and removes the account's data on its way ({@link RequireSession}).
 *
 * @param queryClient - The query client of the app.
 * @param reason - Why the session ended, which decides whether sign-in returns to the page.
 */
export function endSession(queryClient: QueryClient, reason: SignedOutReason): void {
  const state: SessionState = { kind: "signed_out", reason };
  queryClient.setQueryData(sessionQueryKeys.current(), state);
}
