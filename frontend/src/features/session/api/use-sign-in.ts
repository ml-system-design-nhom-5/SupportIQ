/**
 * Sign in (`createSession`). It takes no `Idempotency-Key` and is never retried automatically
 * (TS-29, CON-13).
 */
import { useMutation, type UseMutationResult, useQueryClient } from "@tanstack/react-query";

import { type BackendClient, useBackendClient } from "@/api/client";
import { isUnauthenticatedError, requestData } from "@/features/backend-requests";
import { startSession } from "@/features/session/api/session-cache";
import { InvalidCredentialsError } from "@/features/session/model/invalid-credentials-error";
import { type Session, toSession } from "@/features/session/model/session";

/** What the person typed. The password is Secret: it is sent once and never stored or logged. */
export type SignInCredentials = {
  readonly loginName: string;
  readonly password: string;
};

/**
 * Sign in. On success the previous account's cached data and every sign-in attempt are removed,
 * and the new session is recorded (switching accounts never shows the previous account's data).
 *
 * @returns The mutation; it is never retried.
 */
export function useSignIn(): UseMutationResult<Session, Error, SignInCredentials> {
  const client = useBackendClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: SignInCredentials) => signIn(client, credentials),
    retry: false,
    onSuccess: (session) => {
      startSession(queryClient, session);
    },
  });
}

/**
 * Send the credentials.
 *
 * @param client - The backend client.
 * @param credentials - The login name and the password.
 * @returns The signed-in account.
 * @throws InvalidCredentialsError for the `401` of a refused sign-in.
 * @throws RequestFailureError for any other failure.
 */
async function signIn(client: BackendClient, credentials: SignInCredentials): Promise<Session> {
  try {
    return await requestData(
      () =>
        client.POST("/v1/sessions", {
          body: { login_name: credentials.loginName, password: credentials.password },
        }),
      toSession,
    );
  } catch (error) {
    if (isUnauthenticatedError(error)) {
      throw new InvalidCredentialsError();
    }
    throw error;
  }
}
