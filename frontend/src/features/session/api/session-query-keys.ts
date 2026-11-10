/**
 * The query keys of the session feature (TS-19).
 */
import type { QueryKey } from "@tanstack/react-query";

/** The one key factory of the session feature. */
export const sessionQueryKeys = {
  all: ["session"] as const,
  current: () => [...sessionQueryKeys.all, "current"] as const,
};

/**
 * Tell whether a query belongs to the session feature.
 *
 * @param queryKey - The key of a cached query.
 * @returns True for the session queries, which survive a change of account.
 */
export function isSessionQueryKey(queryKey: QueryKey): boolean {
  return queryKey[0] === sessionQueryKeys.all[0];
}
