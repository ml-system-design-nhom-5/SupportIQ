/**
 * Sign out (`deleteCurrentSession`). It takes no `Idempotency-Key` and is never retried
 * automatically; a `401` means that the session already ended, which is treated as signed out
 * (TS-29, CON-13).
 */
import { useMutation, type UseMutationResult, useQueryClient } from "@tanstack/react-query";

import { type BackendClient, useBackendClient } from "@/api/client";
import { isUnauthenticatedError, requestNoContent } from "@/features/backend-requests";
import { endSession } from "@/features/session/api/session-cache";

/**
 * Sign out. On success every cached response of the account is removed.
 *
 * @returns The mutation; it is never retried.
 */
export function useSignOut(): UseMutationResult<void, Error, void> {
  const client = useBackendClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => signOut(client),
    retry: false,
    onSuccess: () => {
      endSession(queryClient, "signed_out_by_user");
    },
  });
}

/**
 * Delete the current session.
 *
 * @param client - The backend client.
 * @throws RequestFailureError for any failure except `401`.
 */
async function signOut(client: BackendClient): Promise<void> {
  try {
    await requestNoContent(() => client.DELETE("/v1/sessions/current"));
  } catch (error) {
    if (!isUnauthenticatedError(error)) {
      throw error;
    }
  }
}
