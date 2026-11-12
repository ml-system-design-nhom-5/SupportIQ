/**
 * Checks of what the query client of a test still holds. A password exists only in the open form
 * and in the request: never in a query or mutation cache after the request settles (account
 * management design, Shared behavior).
 */
import type { QueryClient } from "@tanstack/react-query";
import { expect } from "vitest";

/**
 * Fail when the variables of a cached mutation or the data of a cached query hold a value.
 *
 * @param queryClient - The query client of the test.
 * @param value - The value, such as a password that the test typed.
 */
export function expectNotCached(queryClient: QueryClient, value: string): void {
  const cachedValues = JSON.stringify([
    queryClient
      .getMutationCache()
      .getAll()
      .map((mutation) => mutation.state.variables),
    queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.state.data),
  ]);

  expect(cachedValues).not.toContain(value);
}
