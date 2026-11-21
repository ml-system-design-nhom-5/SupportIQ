/**
 * Idempotency keys and the retry defaults of writes that carry one (TS-29, ERR-15).
 *
 * A key is created when the person confirms an action. TanStack Query keeps the mutation's
 * variables for its automatic retries, so a retry sends the same key. A repeated action keeps its
 * key too: the same text sent again (shop UI design, Flow), or the same change confirmed again
 * after a failure (admin UI design, Flow). Any other action gets a new key. A form whose fields
 * hold a password keeps its key until a field changes, because `backend` leaves passwords out of
 * the comparison of keys (account management design, Idempotency).
 */
import type { MutationKey, QueryClient } from "@tanstack/react-query";
import { createContext, use, useRef } from "react";

import {
  getRequestFailure,
  isRefusedByBackend,
  isWriteOutcomeUnknown,
  RequestFailureError,
} from "@/features/backend-requests/model/request-failure";

/**
 * Every mutation that sends an `Idempotency-Key` starts its mutation key with this prefix. The
 * composition root gives these mutations, and only these, the automatic retry policy.
 */
export const idempotentWriteMutationKey = ["idempotent-write"] as const;

/** Creates the key of one user action. The composition root provides it (ARCH-31). */
export const IdempotencyKeyFactoryContext = createContext<(() => string) | null>(null);

/** The key of the write of one form: one key for one set of field values. */
export type FormIdempotencyKey = {
  /** Returns the key of the current field values, and creates it at their first submission. */
  readonly getOrCreateKey: () => string;
  /** Forgets the key because a field changed, so the next submission gets a new one. */
  readonly forgetKey: () => void;
};

/** Sends one attempt of a write with a key, and keeps track of unknown outcomes. */
type WriteAttemptSender = <Data>(
  idempotencyKey: string,
  send: () => Promise<Data>,
) => Promise<Data>;

/**
 * Build the mutation key of a write that sends an `Idempotency-Key`.
 *
 * @param operationId - The contract operation, for example `createShopTicket`.
 * @returns The mutation key.
 */
export function buildIdempotentWriteKey(
  operationId: string,
): readonly [...typeof idempotentWriteMutationKey, string] {
  return [...idempotentWriteMutationKey, operationId];
}

/**
 * Read the factory of idempotency keys.
 *
 * @returns A function that creates a new key: a lowercase UUID, as the contract requires.
 * @throws Error when no composition root provides the factory.
 */
export function useCreateIdempotencyKey(): () => string {
  const createKey = use(IdempotencyKeyFactoryContext);
  if (createKey === null) {
    throw new Error("useCreateIdempotencyKey needs IdempotencyKeyFactoryContext.");
  }
  return createKey;
}

/**
 * Keep the `Idempotency-Key` of a form (account management design, Shared behavior). Submitting
 * the same field values again after a failure reuses it; any edit, a password field included,
 * creates a new key. The form calls `forgetKey` whenever a field changes.
 *
 * @returns The key of the current field values, and the function that forgets it.
 */
export function useFormIdempotencyKey(): FormIdempotencyKey {
  const createKey = useCreateIdempotencyKey();
  const keyRef = useRef<string | undefined>(undefined);
  return {
    getOrCreateKey: () => {
      keyRef.current ??= createKey();
      return keyRef.current;
    },
    forgetKey: () => {
      keyRef.current = undefined;
    },
  };
}

/**
 * Remove the writes with a mutation key from the mutation cache. A write whose variables hold a
 * password calls it when it settles, so the password stays only in the open form and in the request
 * (account management design, Shared behavior). The screen keeps the outcome that it shows.
 *
 * @param queryClient - The query client of the app.
 * @param mutationKey - The mutation key of the write.
 */
export function forgetWrites(queryClient: QueryClient, mutationKey: MutationKey): void {
  const mutationCache = queryClient.getMutationCache();
  for (const mutation of mutationCache.findAll({ mutationKey, exact: true })) {
    mutationCache.remove(mutation);
  }
}

/**
 * Remember, for each key, whether an attempt had an unknown outcome. Only the last failure reaches
 * the UI, and it can hide an earlier one: after a lost connection, a retry that gets `503` says
 * nothing about the first attempt, which `backend` may still finish.
 *
 * @returns A function that runs every attempt of a write. A later failure with the same key is
 *   marked as following an unknown outcome, unless `backend` itself refused it.
 */
export function useWriteAttemptSender(): WriteAttemptSender {
  const keysWithUnknownOutcome = useRef(new Set<string>());
  return async (idempotencyKey, send) => {
    try {
      return await send();
    } catch (error) {
      const failure = getRequestFailure(error);
      if (failure === undefined) {
        throw error;
      }
      if (isWriteOutcomeUnknown(failure)) {
        keysWithUnknownOutcome.current.add(idempotencyKey);
      }
      if (keysWithUnknownOutcome.current.has(idempotencyKey) && !isRefusedByBackend(failure)) {
        throw new RequestFailureError(
          { ...failure, isAfterUnknownOutcome: true },
          { cause: error },
        );
      }
      throw error;
    }
  };
}
