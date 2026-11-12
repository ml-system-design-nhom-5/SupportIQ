/**
 * Change the own password (`changeOwnPassword`). Automatic retries reuse the `Idempotency-Key`, and
 * so does sending the same fields again after a failure (TS-29; account management design,
 * Idempotency). The passwords are Secret: the write leaves the mutation cache when it settles, so
 * they exist only in the open form and in the request.
 */
import { useMutation, type UseMutationResult, useQueryClient } from "@tanstack/react-query";

import { type BackendClient, useBackendClient } from "@/api/client";
import {
  buildIdempotentWriteKey,
  forgetWrites,
  requestData,
  useWriteAttemptSender,
} from "@/features/backend-requests";
import { replaceCachedSession } from "@/features/session/api/session-cache";
import type { PasswordChange } from "@/features/session/model/password-change";
import { type Session, toSession } from "@/features/session/model/session";

const changeOwnPasswordKey = buildIdempotentWriteKey("changeOwnPassword");

/** One submission of the form. */
export type OwnPasswordChange = PasswordChange & {
  /** Stays while the fields stay the same (account management design, Shared behavior). */
  readonly idempotencyKey: string;
};

/**
 * Change the password of the signed-in account. On success the cached session is replaced with the
 * answer of `backend`.
 *
 * @returns The mutation; its key gives it the retry policy of idempotent writes.
 */
export function useChangeOwnPassword(): UseMutationResult<Session, Error, OwnPasswordChange> {
  const client = useBackendClient();
  const queryClient = useQueryClient();
  const sendAttempt = useWriteAttemptSender();
  return useMutation({
    mutationKey: changeOwnPasswordKey,
    mutationFn: (change: OwnPasswordChange) =>
      sendAttempt(change.idempotencyKey, () => changeOwnPassword(client, change)),
    onSuccess: (session) => {
      replaceCachedSession(queryClient, session);
    },
    onSettled: () => {
      forgetWrites(queryClient, changeOwnPasswordKey);
    },
  });
}

/**
 * Send the change.
 *
 * @param client - The backend client.
 * @param change - The passwords, the sign-out choice, and the key.
 * @returns The signed-in account.
 */
function changeOwnPassword(client: BackendClient, change: OwnPasswordChange): Promise<Session> {
  return requestData(
    () =>
      client.POST("/v1/sessions/current/password-changes", {
        params: { header: { "Idempotency-Key": change.idempotencyKey } },
        body: {
          current_password: change.currentPassword,
          new_password: change.newPassword,
          is_signed_out_elsewhere: change.isSignedOutElsewhere,
        },
      }),
    toSession,
  );
}
