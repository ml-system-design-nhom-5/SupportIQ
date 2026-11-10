/**
 * Read the signed-in account (`getCurrentSession`). A `401` is not an error here: it means that
 * nobody is signed in.
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { type BackendClient, useBackendClient } from "@/api/client";
import { isUnauthenticatedError, requestData } from "@/features/backend-requests";
import { sessionQueryKeys } from "@/features/session/api/session-query-keys";
import { type SessionState, toSession } from "@/features/session/model/session";

/**
 * Read the session state.
 *
 * @returns The query of the session state.
 */
export function useCurrentSession(): UseQueryResult<SessionState> {
  const client = useBackendClient();
  return useQuery({
    queryKey: sessionQueryKeys.current(),
    queryFn: ({ signal }) => fetchSessionState(client, signal),
  });
}

/**
 * Read the account ID of the signed-in account, for a screen that must find the caller's own
 * record (admin UI design, Data and contracts).
 *
 * @returns The `account_id`, or undefined until a session is known.
 */
export function useSignedInAccountId(): string | undefined {
  const { data: sessionState } = useCurrentSession();
  return sessionState?.kind === "signed_in" ? sessionState.session.accountId : undefined;
}

/**
 * Fetch the session state.
 *
 * @param client - The backend client.
 * @param signal - Cancels the request when the query is cancelled.
 * @returns Signed in with the account, or signed out after a `401`.
 * @throws RequestFailureError for any other failure.
 */
async function fetchSessionState(
  client: BackendClient,
  signal: AbortSignal,
): Promise<SessionState> {
  try {
    const session = await requestData(
      () => client.GET("/v1/sessions/current", { signal }),
      toSession,
    );
    return { kind: "signed_in", session };
  } catch (error) {
    if (isUnauthenticatedError(error)) {
      return { kind: "signed_out", reason: "no_valid_session" };
    }
    throw error;
  }
}
