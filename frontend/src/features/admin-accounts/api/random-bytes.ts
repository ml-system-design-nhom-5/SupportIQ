/**
 * The random source of the suggested passwords (account management design, Suggested passwords).
 * The composition root provides `crypto.getRandomValues` (ARCH-31, CODE-18); tests and stories
 * provide a fixed source.
 */
import { createContext, use } from "react";

import type { RandomBytes } from "@/features/admin-accounts/model/suggested-password";

/** Holds the random source that the composition root provides. */
export const RandomBytesContext = createContext<RandomBytes | null>(null);

/**
 * Read the random source.
 *
 * @returns The function that returns random bytes.
 * @throws Error when no composition root provides the source.
 */
export function useRandomBytes(): RandomBytes {
  const randomBytes = use(RandomBytesContext);
  if (randomBytes === null) {
    throw new Error("useRandomBytes needs RandomBytesContext.");
  }
  return randomBytes;
}
