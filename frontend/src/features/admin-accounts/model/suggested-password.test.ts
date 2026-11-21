import { describe, expect, it } from "vitest";

import {
  buildSuggestedPassword,
  type RandomBytes,
} from "@/features/admin-accounts/model/suggested-password";

/** Three groups of four symbols, without i, l, o, and u, joined by hyphens. */
const suggestionPattern = /^[0-9a-hjkmnp-tv-z]{4}-[0-9a-hjkmnp-tv-z]{4}-[0-9a-hjkmnp-tv-z]{4}$/;

const SUGGESTION_LENGTH = 14;

/**
 * Build a fixed random source (TEST-14).
 *
 * @param bytes - The 12 bytes that it returns.
 * @returns The source.
 */
function fixedSource(bytes: readonly number[]): RandomBytes {
  return () => Uint8Array.from(bytes);
}

describe("buildSuggestedPassword (account management design, Suggested passwords)", () => {
  it.each([
    ["the first symbols", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], "0123-4567-89ab"],
    ["the last symbols", [20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31], "mnpq-rstv-wxyz"],
    ["bytes above 31", [32, 63, 64, 95, 128, 159, 224, 255, 50, 51, 52, 53], "0z0z-0z0z-jkmn"],
  ])("maps one byte to one symbol, for %s", (_case, bytes, password) => {
    const suggestion = buildSuggestedPassword(fixedSource(bytes));

    expect(suggestion).toHaveLength(SUGGESTION_LENGTH);
    expect(suggestion).toMatch(suggestionPattern);
    expect(suggestion).toBe(password);
  });
});
