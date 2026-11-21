/**
 * The exhaustiveness check at the end of every `switch` over a union (TS-12).
 */

/**
 * Stop at a value that no case of a `switch` handled. The compiler rejects the call when a case
 * is missing, and the error reports a value that reached it at runtime anyway.
 *
 * @param value - The value that no case handled.
 * @returns Never.
 * @throws Error always.
 */
export function assertNever(value: never): never {
  throw new Error(`No case handled the value ${JSON.stringify(value)}.`);
}
