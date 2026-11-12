/**
 * The password that the create and reset dialogs suggest (account management design, Suggested
 * passwords): 12 symbols in three groups of four, joined by hyphens, such as `k3m9-x7c2-q8vh`. The
 * hyphens are part of the password. The generator is a pure function of a random source: the
 * composition root gives it `crypto.getRandomValues`, and tests give it a fixed source (CODE-18).
 */

/**
 * The digits and the lowercase letters except i, l, o, and u, so that the password reads clearly.
 * There are 32 of them, which divides 256, so each random byte maps to one with equal weight.
 */
const SUGGESTION_SYMBOLS = "0123456789abcdefghjkmnpqrstvwxyz";

const GROUP_COUNT = 3;

const GROUP_LENGTH = 4;

const GROUP_SEPARATOR = "-";

/** Returns as many random bytes as asked for, such as `crypto.getRandomValues` fills. */
export type RandomBytes = (count: number) => Uint8Array;

/**
 * Build a suggested password.
 *
 * @param randomBytes - The random source: one byte for each symbol.
 * @returns 14 characters: three groups of four symbols with a hyphen between groups.
 */
export function buildSuggestedPassword(randomBytes: RandomBytes): string {
  const symbols = Array.from(randomBytes(GROUP_COUNT * GROUP_LENGTH), (byte) =>
    SUGGESTION_SYMBOLS.charAt(byte % SUGGESTION_SYMBOLS.length),
  );
  return Array.from({ length: GROUP_COUNT }, (_unused, groupIndex) =>
    symbols.slice(groupIndex * GROUP_LENGTH, (groupIndex + 1) * GROUP_LENGTH).join(""),
  ).join(GROUP_SEPARATOR);
}
