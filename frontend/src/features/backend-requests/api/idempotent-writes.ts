/**
 * Idempotency keys and the retry defaults of writes that carry one (TS-29, ERR-15).
 *
 * A key is created when the person confirms an action. TanStack Query keeps the mutation's
 * variables for its automatic retries, so a retry sends the same key. A repeated action keeps its
 * key too: the same text sent again (shop UI design, Flow), or the same change confirmed again
 * after a failure (admin UI design, Flow). Any other action gets a new key.
 */
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
